import json
import boto3
import streamlit as st
from PIL import Image, ImageOps
import websocket
import uuid
import random
import os
import io
import requests
import base64
from streamlit_cognito_auth import CognitoAuthenticator
from botocore.exceptions import ClientError
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    layout="wide",
    page_title="Personalized Generative AI Avatars"
)

image_moderation = True

bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')

COMFYUI_ENDPOINT = f"{os.environ.get('COMFYUI')}:8181"

bucket = os.environ.get("S3_BUCKET")
prefix = os.environ.get("S3_BUCKET_PREFIX")

local_path = "/tmp/"
input_dir = "/tmp/input"
output_dir = "/tmp/output"
workflowfile = "dreamshaper_api.json"
scifi_presets_json = 'presets_scifi_prompts.json'
football_presets_json = 'presets_football_prompts.json'
sports_presets_json = 'presets_sports_prompts.json'
negative_prompt_file = 'negative_prompts.json'

# Check for the existence of each directory, and create it if it doesn't exist
os.makedirs(input_dir, exist_ok=True)
os.makedirs(output_dir, exist_ok=True)

pool_id = os.environ["COGNITO_POOL_ID"]
app_client_id = os.environ["COGNITO_APP_CLIENT_ID"]
app_client_secret = os.environ["COGNITO_APP_CLIENT_SECRET"]

authenticator = CognitoAuthenticator(
    pool_id=pool_id,
    app_client_id=app_client_id,
    app_client_secret=app_client_secret,
    use_cookies=True
)

# Initialize session state variables
session_state_defaults = {
    "glb_photo_name": 'placeholder',
    "rekog_img_labels": [],
    "displayed_avatar": st.text(""),
    "response_body": st.text(""),
    "avatar_created": False,
    "face_detected": None,
    "log_messages": [],
    "authenticated": False,
    "filename": None,
    "capture": True,
    "file_uploader_key": 0
}
for key, value in session_state_defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# Initialize comfyui_session if not present
if 'comfyui_session' not in st.session_state:
    st.session_state.comfyui_session = str(uuid.uuid4())

comfyui_session = st.session_state.comfyui_session
client_id = str(uuid.uuid4())

logger.info(f"Using comfyui_session: {comfyui_session}")
logger.info(f"Using client_id: {client_id}")

# Random initialization of the customization buttons
rnd_max_values = {
    "rnd1": 59,
    "rnd2": 19,
    "rnd3": 9,
    "rnd4": 59,
    "rnd5": 9,
    "rnd6": 9,
    "rnd7": 19,
    "rnd8": 19
}
for rnd_key, rnd_max in rnd_max_values.items():
    if rnd_key not in st.session_state:
        st.session_state[rnd_key] = random.random() * rnd_max

# AWS clients
if image_moderation:
    session = boto3.Session()
    client = session.client('rekognition')
    s3 = boto3.resource('s3')

def make_comfyui_request(endpoint, method='GET', data=None, headers=None, files=None, params=None, cookies=None):
    url = f"http://{COMFYUI_ENDPOINT}/{endpoint}"
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, params=params, cookies=cookies)
            logger.info(f"make_comfyui_request GET response: {response}")
        elif method == 'POST':
            response = requests.post(url, data=data, headers=headers, files=files, params=params, cookies=cookies)
            logger.info(f"make_comfyui_request POST response: {response}")
        else:
            raise ValueError(f"Unsupported method {method}")
        response.raise_for_status()
        if response.headers.get('Content-Type', '').startswith('application/json'):
            return response.json()
        else:
            return response.content
    except requests.exceptions.HTTPError as e:
        st.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Error making request to ComfyUI: {e}")
        return None


def create_ws_connection():
    
    comfyui_session = st.session_state.get('comfyui_session', '')
    # Build cookie string with only 'comfyui_session'
    cookie_str = f'COMFY-SESSION={comfyui_session}'
    ws = websocket.WebSocket()
    logger.info(f"Creating WebSocket connection with comfyui_session: {comfyui_session}")
    ws.connect(f"ws://{COMFYUI_ENDPOINT}/ws?clientId={client_id}", cookie=cookie_str)
    return ws


def is_comfyui_running():
    try:
        response = make_comfyui_request('system_stats')
        return response is not None
    except Exception:
        return False

def clear_session_state():
    keys_to_clear = [
        "img_file_buffer",
        "filename",
        "avatar_final_image",
        "glb_photo_name",
        "rekog_img_labels",
        "displayed_avatar",
        "response_body",
        "avatar_created",
        "face_detected"
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    # Reset random values
    for rnd_key in rnd_max_values.keys():
        st.session_state[rnd_key] = random.random() * rnd_max_values[rnd_key]

def get_authenticated_status():
    is_logged_in = authenticator.login()
    return is_logged_in

is_logged_in = get_authenticated_status()
if is_logged_in:
    if not st.session_state.get('authenticated'):
        clear_session_state()  # Clear session state for new login
    st.session_state['authenticated'] = True
if not is_logged_in:
    st.stop()

def moderate_image(photo, bucket):
    response = client.detect_moderation_labels(Image={'S3Object': {'Bucket': bucket, 'Name': photo}})
    return len(response['ModerationLabels'])

class RekognitionImage:

    def __init__(self, image, image_name, rekognition_client):
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()
        self.image = img_byte_arr
        self.image_name = image_name
        self.rekognition_client = rekognition_client

    def detect_faces(self):
        try:
            response = self.rekognition_client.detect_faces(
                Image={'Bytes': self.image},
                Attributes=['ALL']
            )
            face_details = response['FaceDetails']
            return len(face_details) > 0
        except ClientError:
            print(f"Couldn't detect faces in {self.image_name}")
            return False

    def detect_moderation_labels(self):
        response = self.rekognition_client.detect_moderation_labels(
            Image={'Bytes': self.image}
        )
        labels = [label['Name'] for label in response["ModerationLabels"]]
        return labels

def created_avatar():
    st.session_state["avatar_created"] = True
    st.session_state["glb_photo_name"] = "avatar-" + str(uuid.uuid4())[-17:] + ".jpeg"
    if st.session_state.get("displayed_avatar"):
        st.session_state["displayed_avatar"].empty()

def upload_image(input_path, name, comfyui_session, image_type="input", overwrite=False):
    with open(input_path, 'rb') as file:
        files = {
            'image': (name, file, 'image/jpeg'),
        }
        data = {
            'type': image_type,
            'overwrite': str(overwrite).lower()
        }
        cookies = {'COMFY-SESSION': comfyui_session}
        return make_comfyui_request('upload/image', method='POST', data=data, files=files, cookies=cookies)


def share_avatar(image_data):
    output_image_name = local_path + "output/" + st.session_state["glb_photo_name"]
    image_data.save(output_image_name)
    if image_moderation:
        s3_key = prefix + st.session_state["glb_photo_name"]
        s3.meta.client.upload_file(output_image_name, bucket, s3_key)

def parse_workflow(ws, prompt, negative_prompt, seed, input_image_name, filename, comfyui_session):
    image.convert('RGB').save(input_image_name, "JPEG")
    with open(workflowfile, 'r', encoding="utf-8") as workflow_api_txt2gif_file:
        # First upload Image to ComfyUI
        upload_image(input_image_name, filename, comfyui_session, overwrite=True)
        prompt_data = json.load(workflow_api_txt2gif_file)
        # Set prompts and seed
        prompt_data["46"]["inputs"]["text"] = prompt
        prompt_data["47"]["inputs"]["text"] = negative_prompt
        prompt_data["45"]["inputs"]["noise_seed"] = seed
        prompt_data["53"]["inputs"]["image"] = filename
        return get_images(ws, prompt_data, input_image_name, comfyui_session)


def queue_prompt(prompt):
    comfyui_session = st.session_state.comfyui_session
    data = {"prompt": prompt, "client_id": client_id}
    headers = {'Content-Type': 'application/json'}
    cookies = {'COMFY-SESSION': comfyui_session}
    logger.info(f"Queueing prompt with data: {data}")
    response = requests.post(f"http://{COMFYUI_ENDPOINT}/prompt", data=json.dumps(data).encode("utf-8"), cookies=cookies)
    response.raise_for_status()
    return response.json()


def preprocess_image(uploaded_file, max_size=1024):
    try:
        # Read file content
        file_content = uploaded_file.read()

        # Open the image
        with Image.open(io.BytesIO(file_content)) as img:
            # Convert to RGB (removes alpha channel if present)
            img = img.convert('RGB')

            # Get the larger dimension
            max_dim = max(img.width, img.height)

            # Only resize if the image is larger than max_size
            if max_dim > max_size:
                # Calculate the ratio
                ratio = max_size / max_dim
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.LANCZOS)

            # Save to bytes as PNG
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            return img_byte_arr.getvalue()
    except Exception as e:
        st.error(f"Error processing image: {str(e)}")
        return None

def get_history(prompt_id):
    cookies = {'COMFY-SESSION': comfyui_session}

    logger.info(f"get_history prompt_id: {prompt_id}")
    logger.info(f"get_history comfyui_session: {comfyui_session}")
    response = requests.get(f"http://{COMFYUI_ENDPOINT}/history/{prompt_id}", cookies=cookies)
    logger.info(f"get_history response: {response.json()}")
    response.raise_for_status()
    return response.json()

def get_image(filename, subfolder, folder_type, comfyui_session):
    params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    cookies = {'COMFY-SESSION': comfyui_session}
    response = requests.get(f"http://{COMFYUI_ENDPOINT}/view", params=params, cookies=cookies)
    response.raise_for_status()
    return response.content

def get_images(ws, prompt, input_image_name, comfyui_session):
    response = queue_prompt(prompt)
    logger.info(f"get_images response: {response}")
    if response is None:
        st.error("Failed to queue prompt.")
        return {}
    prompt_id = response.get('prompt_id')
    logger.info(f"get_images prompt_id: {prompt_id}")
    if not prompt_id:
        st.error("No prompt_id received from server.")
        return {}
    
    # msg = st.toast(f"Processing prompt: {prompt_id}")
    
    output_images = {}
    last_queue_remaining = None
    last_message_time = time.time()
    timeout = 8

    def attempt_fetch_images():
        nonlocal output_images
        try:
            history = get_history(prompt_id)
            if history and prompt_id in history:
                for node_id, node_output in history[prompt_id].get('outputs', {}).items():
                    if 'images' in node_output:
                        images_output = []
                        for image_info in node_output['images']:
                            image_data = get_image(image_info['filename'], image_info['subfolder'], image_info['type'], comfyui_session)
                            images_output.append(image_data)
                        output_images[node_id] = images_output
            return bool(output_images)
        except Exception as e:
            st.error(f"Failed to fetch images: {e}")
            return False

    msg = st.toast('Avatar creation triggered...')
    time.sleep(2)
    overall_timeout = 30

    while True:
        if time.time() - last_message_time > overall_timeout:
            logger.info("Overall timeout reached. Closing connection.")
            break
        
        try:
            out = ws.recv()
            
            if isinstance(out, str):
                message = json.loads(out)
                logger.info(f"ws out message: {message}")
                
                if message['type'] == 'executed':
                    data = message['data']
                    if data['prompt_id'] == prompt_id:
                        node_id = data['node']
                        # msg.toast(f"Node execution completed: {node_id}")
                        if 'output' in data:
                            if 'images' in data['output']:
                                images_output = []
                                for image_info in data['output']['images']:
                                    image_data = get_image(image_info['filename'], image_info['subfolder'], image_info['type'], comfyui_session)
                                    images_output.append(image_data)
                                output_images[node_id] = images_output
                                # msg.toast(f"Images processed for node {node_id}", icon="✅")
                                break  # Exit the loop as we've got our images
                
                elif message['type'] == 'execution_cached':
                    if message['data']['prompt_id'] == prompt_id:
                        logger.info(f"Execution cached: {message['data']}")
                
                elif message['type'] == 'executing':
                    data = message['data']
                    if data['prompt_id'] == prompt_id:
                        if data['node'] is None:
                            logger.info("Execution started.")
                        else:
                            logger.info(f"Executing node: {data['node']}")
                
                elif message['type'] == 'progress':
                    data = message['data']
                    if data['prompt_id'] == prompt_id:
                        logger.info(f"Progress: {data['value']}/{data['max']} on node {data['node']}")
                
                elif message['type'] == 'status':
                    status_data = message['data']['status']
                    if 'exec_info' in status_data:
                        queue_remaining = status_data['exec_info'].get('queue_remaining', 0)
                        logger.info(f"Queue remaining: {queue_remaining}")
                        if queue_remaining == 0:
                            logger.info("Queue processing complete. Checking for images.")
                            if attempt_fetch_images():
                                logger.info("Images fetched successfully after queue completion.", icon="✅")
                                break
                        last_queue_remaining = queue_remaining
            else:
                continue

        except websocket.WebSocketTimeoutException:
            # Check if we've been waiting too long without receiving any message
            msg.toast("only a couple seconds more...")
            if time.time() - last_message_time > timeout:
                if attempt_fetch_images():
                    logger.info("Images fetched successfully after timeout.", icon="✅")
                    break
                else:
                    logger.info("No images found after timeout. Continuing to wait.", icon="⏳")

        except websocket.WebSocketConnectionClosedException as e:
            #st.warning(f"WebSocket connection closed: {e}. Attempting to fetch images.")
            if attempt_fetch_images():
                msg.toast("only a couple seconds more...", icon="✅")
            else:
                logger.info("Failed to fetch images after connection closed.")
            break

        except Exception as e:
            logger.info(f"Error while receiving from WebSocket: {e}")
            break

    ws.close()

    # If still no images, try one last time
    if not output_images:
        msg.toast("only a couple seconds more...", icon="🔄")
        attempt_fetch_images()

    if not output_images:
        st.error("Failed to fetch the avatar. Please try again")

    msg.toast("Images fetched successfully.", icon="✅")

    # Do not persist input image
    os.remove(input_image_name)
    return output_images


def describe_picture():
    if st.session_state.get("img_file_buffer") is not None:
        with Image.open(st.session_state.get("img_file_buffer")) as image:
            with io.BytesIO() as buf:
                image.save(buf, 'jpeg')
                image_bytes = buf.getvalue()
                encoded_image = base64.b64encode(image_bytes).decode('utf8')

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "messages": [{
                "role": "user",
                "content": [{
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": encoded_image,
                    },
                },
                    {"type": "text", "text": "What is in this image?"}, ],
            }]
        })
        response = bedrock_runtime.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            body=body
        )
        st.session_state["response_body"] = json.loads(response.get("body").read())

def logout():
    clear_session_state()
    authenticator.cookie_manager.reset_credentials()
    authenticator.logout()
    st.stop()

if st.session_state['authenticated']:
    # MAIN PAGE
    st.title('Personalized Generative AI Avatars')
    st.header("", divider='rainbow')

    st.markdown(''' #### :information_source:   Disclaimer  
    - Uploaded user images are :green[deleted after the event]
    - Generated avatars are :green[only displayed in the gallery with consent (click on share avatar)]
    - The application is fully automated. We have included guardails in place to moderate unintented content
    - Powered by AWS Sample: [comfyui-personalized-generative-ai-avatars-app](https://github.com/aws-samples/comfyui-personalized-generative-ai-avatars-app)
    ''', unsafe_allow_html=True)

    if st.button("Logout"):
        logout()

    st.header("",divider='rainbow')

    if 'img_file_buffer' not in st.session_state:
        st.session_state['img_file_buffer'] = None
    
    # Check if Backend (ComfyUI) is available
    comfyui_backend = is_comfyui_running()
    if not comfyui_backend:
        st.warning("Backend (ComfyUI) is not available. Please check your ComfyUI configuration.")
    else:
        st.header("Upload or Capture an Image")
        uploaded_file = st.file_uploader("Click on \"Browse files\"", type=['png', 'jpg', 'jpeg'],
                                         accept_multiple_files=False, key=st.session_state["file_uploader_key"])
        if uploaded_file is not None:
            if st.session_state.get('img_file_buffer') != uploaded_file:
                clear_session_state()
                st.session_state['img_file_buffer'] = uploaded_file
                st.session_state['filename'] = "photo-" + str(uuid.uuid4())[-17:] + ".png"

                # Preprocess and perform face detection
                processed_image = preprocess_image(st.session_state['img_file_buffer'], max_size=1024)
                if processed_image:
                    try:
                        rekog_portrait = RekognitionImage(Image.open(io.BytesIO(processed_image)),
                                                          st.session_state["file_uploader_key"], client)
                        st.session_state['face_detected'] = rekog_portrait.detect_faces()
                    except Exception as e:
                        st.error(f"Face detection error: {str(e)}")
                        st.session_state['face_detected'] = False
                else:
                    st.session_state['face_detected'] = False

    # Display captured image or uploaded image
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.session_state['img_file_buffer'] is not None:
            if st.session_state['filename'] is None:
                st.session_state['filename'] = "photo-" + str(uuid.uuid4())[-17:] + ".jpeg"

            st.header("Uploaded image")
            with Image.open(st.session_state['img_file_buffer']) as image:
                image = ImageOps.exif_transpose(image)
                st.image(image, use_column_width="always")

            if st.button('Clear Image', use_container_width=True):
                clear_session_state()
                st.session_state['file_uploader_key'] += 1
                st.rerun()

            filename = st.session_state['filename']
            input_image_name = local_path + "input/" + filename

            if st.button('Describe picture', key="describe_picture", on_click=describe_picture, use_container_width=True):
                if st.session_state["response_body"]:
                    try:
                        st.markdown(
                            f"""
                            <div style="background-color: rgb(27, 29, 37); padding: 10px; border-radius: 10px;">
                                <strong>Extracted description:</strong><br>{st.session_state["response_body"]["content"][0]["text"]}
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    except:
                        st.markdown(
                            f"""
                            <div style="background-color: rgb(27, 29, 37); padding: 10px; border-radius: 10px;">
                                Tried to extract a description of the picture but did not succeed
                            </div>
                            """,
                            unsafe_allow_html=True
                        )

            with col2:
                st.header("Customization options")
                if st.session_state['face_detected'] is False:
                    st.session_state["avatar_final_image"] = ""
                    st.warning("No face detected in the uploaded image. Please try again with a different image.")
                else:
                    with open(scifi_presets_json, 'r', encoding='utf-8') as scifi_json_file:
                        scifi_presets = json.load(scifi_json_file)
                    with open(football_presets_json, 'r', encoding='utf-8') as football_json_file:
                        football_presets = json.load(football_json_file)
                    with open(sports_presets_json, 'r', encoding='utf-8') as sports_json_file:
                        sports_presets = json.load(sports_json_file)

                    with open(negative_prompt_file, 'r', encoding='utf-8') as negative_prompt:
                        negative_prompt_data = json.load(negative_prompt)

                    # Create a dictionary from the data for quick access
                    negative_prompt_dict = {item['negative_prompt']: item['prompt'] for item in negative_prompt_data}

                    # Set negative prompt default
                    negative_prompt = negative_prompt_dict.get('default', '')

                    seed = int(random.random() * 1e8)

                    option = st.selectbox(
                        'Choose a preset style',
                        ['Sci-Fi', 'EURO 2024', 'Other Sports'])

                    if "Sci-Fi" in option:
                        preset_options = [preset['Element_Preset'] for preset in scifi_presets]
                        index_option = round(st.session_state["rnd1"] / rnd_max_values["rnd1"]) % len(preset_options)

                        avatar_preset = st.radio("Presets",
                                                 preset_options,
                                                 horizontal=True,
                                                 index=index_option,
                                                 label_visibility="collapsed")
                        selected_preset = next((item for item in scifi_presets if item['Element_Preset'] == avatar_preset), None)
                        scifi_negative_prompt = negative_prompt_dict.get('scifi', '')

                    if "EURO 2024" in option:
                        preset_options = [preset['Club'] for preset in football_presets]
                        index_option = round(st.session_state["rnd1"] / rnd_max_values["rnd1"]) % len(preset_options)
                        avatar_preset = st.radio("Presets",
                                                 preset_options,
                                                 horizontal=True,
                                                 index=index_option,
                                                 label_visibility="collapsed")

                        selected_preset = next((item for item in football_presets if item['Club'] == avatar_preset), None)
                        football_negative_prompt = negative_prompt_dict.get('football', '')

                    if "Other Sports" in option:
                        preset_options = [preset['Club'] for preset in sports_presets]
                        index_option = round(st.session_state["rnd1"] / rnd_max_values["rnd1"]) % len(preset_options)
                        avatar_preset = st.radio("Presets",
                                                 preset_options,
                                                 horizontal=True,
                                                 index=index_option,
                                                 label_visibility="collapsed")

                        selected_preset = next((item for item in sports_presets if item['Club'] == avatar_preset), None)
                        sports_negative_prompt = negative_prompt_dict.get('other sports', '')

                    preset_prompt = selected_preset['prompt'] if selected_preset else "No prompt found."

                    st.session_state["disable_shot_type"] = False

                    avatar_gender = st.radio("Gender",
                                             ["Man", "Woman", "Nonbinary"], horizontal=True,
                                             index=round(st.session_state["rnd2"] / rnd_max_values["rnd2"]))
                    if avatar_gender == "Man":
                        preset_prompt = preset_prompt.replace("gender", "male")
                    elif avatar_gender == "Woman":
                        preset_prompt = preset_prompt.replace("gender", "female")
                    else:
                        preset_prompt = preset_prompt.replace("gender", "nonbinary gender")

                    avatar_hair = st.radio("Hair length",
                                           ["Short", "Medium", "Long", "No Hair"], horizontal=True,
                                           index=round(st.session_state["rnd3"] / rnd_max_values["rnd3"]))

                    if avatar_hair == "No Hair":
                        avatar_hair_color = "no color"
                    else:
                        avatar_hair_color = st.radio("Hair color",
                                                     ["Blonde", "Brown", "Black", "Red", "Blue", "Green", "Purple",
                                                      "Grey", "Random"], horizontal=True,
                                                     index=round(st.session_state["rnd4"] / rnd_max_values["rnd4"]))

                    avatar_skin_tone = st.radio("Skin Tone",
                                                ["Light", "Medium", "Dark"], horizontal=True,
                                                index=round(st.session_state["rnd7"] / rnd_max_values["rnd7"]))

                    avatar_face_expr = st.radio("Facial Expression",
                                                ["Serious", "Happy"], horizontal=True,
                                                index=round(st.session_state["rnd8"] / rnd_max_values["rnd8"]))

                    if avatar_hair == "No Hair":
                        features = f"{avatar_face_expr} face, {avatar_skin_tone} skin tone, {avatar_hair}, bald,  "
                    else:
                        features = f"{avatar_face_expr} face, {avatar_skin_tone} skin tone, {avatar_hair} {avatar_hair_color} hair, "

                    preset_prompt = preset_prompt.replace("Features:", "Features: " + features)

                    prompt = preset_prompt

                    st.markdown(
                        f"""
                        **Prompt:**
                        <div style="background-color: rgb(27, 29, 37); padding: 10px; border-radius: 10px;">
                            {prompt}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                    st.session_state["avatar_created"] = False

                    # When creating the avatar:
                    if st.button('Create avatar', key="create_avatar", on_click=created_avatar, use_container_width=True):
                        ws = create_ws_connection()
                        if ws:
                            images = parse_workflow(ws, prompt, negative_prompt, seed, input_image_name, filename, comfyui_session)
                        else:
                            st.error("Failed to establish WebSocket connection. Please try again.")

                        st.session_state["avatar_final_image"] = ""
                        for node_id in images:
                            for image_output in images[node_id]:
                                image_data = Image.open(io.BytesIO(image_output))
                                st.session_state["avatar_final_image"] = image_data
                                if image_moderation:
                                    rekog_img = RekognitionImage(st.session_state["avatar_final_image"],
                                                                st.session_state["glb_photo_name"], client)
                                    st.session_state["rekog_img_labels"] = rekog_img.detect_moderation_labels()
                                    print("Moderation labels detected: " + str(st.session_state["rekog_img_labels"]))

                with col3:
                    st.header("Generated Avatar")
                    if st.session_state.get("avatar_final_image"):
                        if st.session_state["glb_photo_name"] != 'placeholder':
                            # Show Avatar
                            if len(st.session_state["rekog_img_labels"]) == 0:
                                st.session_state["displayed_avatar"] = st.image(st.session_state["avatar_final_image"],
                                                                                caption='Avatar',
                                                                                use_column_width="always",
                                                                                output_format="PNG")

                                # Share Avatar
                                if st.button('Share your avatar!', key="share_avatar", use_container_width=True,
                                             disabled=st.session_state["avatar_created"]):
                                    share_avatar(st.session_state["avatar_final_image"])
                                    st.text("Image shared to Gallery!")
                            else:
                                st.warning("Image has been moderated and will not be shown")

        st.markdown(
            """<style>
            div[class*="stRadio"] > label > div[data-testid="stMarkdownContainer"] > p {
                font-size: 22px;
            }
            </style>
            """, unsafe_allow_html=True)

        st.markdown(
            """
            <style>
            div.row-widget.stRadio > div > label {
                background-color: rgb(19, 23, 32);
                padding: 5px 10px;
                margin-right: 5px;
                margin-bottom: 5px;
                border-radius: 10px;
                border: 1px solid rgba(250, 250, 250, 0.2);
                display: inline-flex;
                align-items: center;
                justify-content: left;
                min-width: 120px;
                text-align: left;
            }
            div.row-widget.stRadio > div > label:hover {
                border-color: #ff4c4b;
            }
            div.row-widget.stRadio > div > label > div:first-child > div {
                background-color: transparent !important;
                border-color: transparent !important;
            }
            div.row-widget.stRadio > div > label.stRadio > div:first-child > div:after {
                content: '';
            }
            </style>
            """, unsafe_allow_html=True
        )
