import streamlit as st
import boto3
from PIL import Image
import io, os, time
from streamlit_cognito_auth import CognitoAuthenticator
from streamlit_extras.stylable_container import stylable_container
from streamlit_autorefresh import st_autorefresh

st.set_page_config(layout="wide")

s3_client = boto3.client('s3')
bucket_name = os.environ.get("S3_BUCKET")
bucket_prefix = os.environ.get("S3_BUCKET_PREFIX")
pool_id = os.environ["COGNITO_POOL_ID"]
app_client_id = os.environ["COGNITO_APP_CLIENT_ID"]
app_client_secret = os.environ["COGNITO_APP_CLIENT_SECRET"]

authenticator = CognitoAuthenticator(
    pool_id=pool_id,
    app_client_id=app_client_id,
    app_client_secret=app_client_secret,
    use_cookies=True
)

cognito_client = boto3.client('cognito-idp')

def get_user_profile():
    credentials = authenticator.get_credentials()
    response = cognito_client.get_user(AccessToken=credentials.access_token)
    user_attributes = response['UserAttributes']
    
    for attribute in user_attributes:
        if attribute['Name'] == "profile":
            return attribute['Value']
    return None

def is_authorized_profile():
    profile = get_user_profile()
    return profile in ['admin', 'gallery']

def is_admin_profile():
    return get_user_profile() == 'admin'

def get_user_attributes():
    credentials = authenticator.get_credentials()
    response = cognito_client.get_user(AccessToken=credentials.access_token)
    return response['UserAttributes']

def logout():
    authenticator.cookie_manager.reset_credentials()
    authenticator.logout()
    st.stop()
    
def get_authenticated_status():
    is_logged_in = authenticator.login()
    return is_logged_in

def move_image(bucket, source_key, dest_key):
    copy_source = {'Bucket': bucket, 'Key': source_key}
    s3_client.copy_object(CopySource=copy_source, Bucket=bucket, Key=dest_key)
    s3_client.delete_object(Bucket=bucket, Key=source_key)

@st.cache_data(ttl=120)
def load_image_from_s3(bucket, key):
    response = s3_client.get_object(Bucket=bucket, Key=key)
    image_content = response['Body'].read()
    image = Image.open(io.BytesIO(image_content))
    return image

@st.cache_data(ttl=60)
def list_images_in_bucket(bucket, prefix):
    images = []
    continuation_token = None
    while True:
        if continuation_token:
            response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix, ContinuationToken=continuation_token)
        else:
            response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        
        images.extend([item['Key'] for item in response.get('Contents', []) if item['Key'].endswith(('.png', '.jpg', '.jpeg'))])
        
        if response.get('IsTruncated'):
            continuation_token = response.get('NextContinuationToken')
        else:
            break
    return images

def display_gallery(images, cols_per_row, is_admin=False):
    col_index = 0
    cols = st.columns(cols_per_row, gap="small")
    for i, image_key in enumerate(images):
        with cols[col_index]:
            img = load_image_from_s3(bucket_name, image_key)
            st.image(img, use_column_width=True)
            if is_admin:
                st.caption(image_key)
                
                if image_key.split("/")[0]+"/" == bucket_prefix:
                    with stylable_container(
                        key=f"green_button_{i}",
                        css_styles="""
                            button {
                                background-color: green;
                                color: white;
                                border-radius: 2px;
                            }
                            """,
                    ):
                        if st.button("promote", key=f'promote_{i}', use_container_width=True):
                            move_image(bucket_name, image_key, f'gallery/{image_key.split("/")[-1]}')
                            st.session_state['refresh_gallery'] = True
                            st.rerun()
                
                if image_key.split("/")[0] == 'gallery':
                    with stylable_container(
                    key=f"red_button_{i}",
                    css_styles="""
                        button {
                            background-color: red;
                            color: white;
                            border-radius: 2px;
                        }
                        """,
                    ):
                        if st.button("moderate", key=f'moderate_{i}', use_container_width=True):
                            move_image(bucket_name, image_key, f'{bucket_prefix}{image_key.split("/")[-1]}')
                            st.session_state['refresh_gallery'] = True
                            st.rerun()
        col_index = (col_index + 1) % cols_per_row
def toggle_auto_refresh():
    st.session_state['auto_refresh'] = not st.session_state.get('auto_refresh', True)

# Main application logic
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False
if 'refresh_gallery' not in st.session_state:
    st.session_state['refresh_gallery'] = False
if 'cols_per_row' not in st.session_state:
    st.session_state['cols_per_row'] = 10
if 'auto_refresh' not in st.session_state:
    st.session_state['auto_refresh'] = True

is_logged_in = get_authenticated_status()

if is_logged_in:
    if is_authorized_profile():
        st.session_state['authenticated'] = True
        st.session_state['is_admin'] = is_admin_profile()
    else:
        st.error("You do not have the required permissions to access this application.")
        logout()
        st.stop()
if not is_logged_in:
    st.stop()

if st.session_state['authenticated']:
    st.markdown("<h1 style='text-align: center;'>🚀 GET YOUR GENERATIVE AI AVATAR 🚀</h1>", unsafe_allow_html=True)
    st.header("",divider='rainbow')
    
    new_cols_per_row = st.sidebar.slider("Columns per row", min_value=1, max_value=25, value=st.session_state['cols_per_row'])
    
    if new_cols_per_row != st.session_state['cols_per_row']:
        st.session_state['cols_per_row'] = new_cols_per_row
        st.session_state['refresh_gallery'] = True
        list_images_in_bucket.clear()
        load_image_from_s3.clear()

    # Add the auto-refresh toggle button to the sidebar
    auto_refresh_text = "Deactivate" if st.session_state['auto_refresh'] else "Activate"
    if st.sidebar.button(f"{auto_refresh_text} Auto-Refresh", use_container_width=True, on_click=toggle_auto_refresh):
        st.rerun()

    st.sidebar.markdown("<h2 style='text-align: center;'>🚀 SCAN THIS QR-CODE 🚀</h1>", unsafe_allow_html=True)
    st.sidebar.markdown("<h3 style='text-align: center;'>user: tbd</h1>", unsafe_allow_html=True)
    st.sidebar.markdown("<h3 style='text-align: center;'>pwd: tbd</h1>", unsafe_allow_html=True)
    st.sidebar.image("qr-code.png")
    
    if st.sidebar.button("Logout", key="logout", use_container_width=True):
        logout()

    # Use st_autorefresh
    if st.session_state['auto_refresh'] and not st.session_state['is_admin']:
        refresh_interval = 60
        st_autorefresh(interval=refresh_interval * 1000, key="datarefresh")

    if st.session_state['is_admin']:
        # Admin-only features
        images = list_images_in_bucket(bucket_name, bucket_prefix)
        images += list_images_in_bucket(bucket_name, 'gallery/')
        display_gallery(images, st.session_state['cols_per_row'], is_admin=True)
    else:
        images = list_images_in_bucket(bucket_name, 'gallery/')
        display_gallery(images, st.session_state['cols_per_row'], is_admin=False)

    # Clear caches if refresh is needed
    if st.session_state['refresh_gallery']:
        st.session_state['refresh_gallery'] = False
        list_images_in_bucket.clear()
        load_image_from_s3.clear()