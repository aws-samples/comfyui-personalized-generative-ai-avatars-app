import json
import boto3
import streamlit as st
from PIL import Image, ImageOps
import websocket
import uuid
import urllib.request
import urllib.parse
import random
import os
import io
from requests_toolbelt import MultipartEncoder
import boto3
import base64
from streamlit_cognito_auth import CognitoAuthenticator
from botocore.exceptions import ClientError

st.set_page_config(
    layout="wide",
    page_title="Personalized Generative AI Avatars"
)

image_moderation = True

bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')

COMFYUI_ENDPOINT=f"{os.environ.get('COMFYUI')}:8181"

bucket= os.environ.get("S3_BUCKET")
prefix= os.environ.get("S3_BUCKET_PREFIX")

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


if not st.session_state.get("glb_photo_name"):
    st.session_state["glb_photo_name"] = 'placeholder'
    
if not st.session_state.get("rekog_img_labels"):
    st.session_state["rekog_img_labels"] = []

if not st.session_state.get("displayed_avatar"):
    st.session_state["displayed_avatar"] = st.text("")

if not st.session_state.get("response_body"):
    st.session_state["response_body"] = st.text("")

if not st.session_state.get("avatar_created"):
    st.session_state["avatar_created"] = False

rnd1_max = 59
rnd2_max = 19
rnd3_max = 9
rnd4_max = 59
rnd5_max = 9
rnd6_max = 9
rnd7_max = 19
rnd8_max = 19

# random initialization of the customization buttons
if not st.session_state.get("rnd1"):
    st.session_state["rnd1"] = random.random()*rnd1_max
if not st.session_state.get("rnd2"):
    st.session_state["rnd2"] = random.random()*rnd2_max
if not st.session_state.get("rnd3"):
    st.session_state["rnd3"] = random.random()*rnd3_max
if not st.session_state.get("rnd4"):
    st.session_state["rnd4"] = random.random()*rnd4_max
if not st.session_state.get("rnd5"):
    st.session_state["rnd5"] = random.random()*rnd5_max
if not st.session_state.get("rnd6"):
    st.session_state["rnd6"] = random.random()*rnd6_max
if not st.session_state.get("rnd7"):
    st.session_state["rnd7"] = random.random()*rnd7_max
if not st.session_state.get("rnd8"):
    st.session_state["rnd8"] = random.random()*rnd8_max

if 'face_detected' not in st.session_state:
    st.session_state['face_detected'] = None

# Initialize the session state for logs if it doesn't exist
if 'log_messages' not in st.session_state:
    st.session_state['log_messages'] = []

def is_comfyui_running():
    url = "http://{}/system_stats".format(COMFYUI_ENDPOINT)
    req = urllib.request.Request(url)

    try:
        response = urllib.request.urlopen(req)
        if response.status == 200:
            return True
        else:
            return False
    except urllib.error.URLError as e:
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
    st.session_state["rnd1"] = random.random()*rnd1_max
    st.session_state["rnd2"] = random.random()*rnd2_max
    st.session_state["rnd3"] = random.random()*rnd3_max
    st.session_state["rnd4"] = random.random()*rnd4_max
    st.session_state["rnd5"] = random.random()*rnd5_max
    st.session_state["rnd6"] = random.random()*rnd6_max
    st.session_state["rnd7"] = random.random()*rnd7_max
    st.session_state["rnd8"] = random.random()*rnd8_max

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

if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

if image_moderation:
    session = boto3.Session()
    client = session.client('rekognition')
    s3 = boto3.resource('s3')
    # bucket='comfyui-avatar'
    # prefix='avatars/'


def moderate_image(photo, bucket):
    response = client.detect_moderation_labels(Image={'S3Object':{'Bucket':bucket,'Name':photo}})

    print('Detected labels for ' + photo)
    for label in response['ModerationLabels']:
        print (label['Name'] + ' : ' + str(label['Confidence']))
        print (label['ParentName'])
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
        # try:
        response = self.rekognition_client.detect_moderation_labels(
            Image={'Bytes': self.image}
        )
        # print("ModerationLabels:",response["ModerationLabels"])
        labels = [
            label['Name']
            for label in response["ModerationLabels"]
        ]
        # print(
            # "Found %s moderation labels in %s.", len(labels), self.image_name
        # )
        # except ClientError:
            # print(
                # "Couldn't detect moderation labels in %s.", self.image_name
            # )
            # raise
        # else:
        return labels

def created_avatar():
    st.session_state["avatar_created"] = True
    st.session_state["glb_photo_name"] = "avatar-"+str(uuid.uuid4())[-17:]+".jpeg"
    if st.session_state.get("displayed_avatar"):
        st.session_state["displayed_avatar"].empty()

def upload_image(input_path, name, server_address, image_type="input", overwrite=False):
  with open(input_path, 'rb') as file:
    multipart_data = MultipartEncoder(
      fields= {
        'image': (name, file, 'image/jpeg'),
        'type': image_type,
        'overwrite': str(overwrite).lower()
      }
    )

    data = multipart_data
    headers = { 'Content-Type': multipart_data.content_type }
    request = urllib.request.Request("http://{}/upload/image".format(server_address), data=data, headers=headers)
    with urllib.request.urlopen(request) as response:
      return response.read()
      
def share_avatar(image_data):
    output_image_name = local_path+"output/"+st.session_state["glb_photo_name"]
    image_data.save(output_image_name)
    if image_moderation:
        s3_key = prefix + st.session_state["glb_photo_name"]
        s3.meta.client.upload_file(output_image_name, bucket, s3_key)


def parse_workflow(ws, prompt,negative_prompt, seed, input_image_name, filename):
    image.convert('RGB').save(input_image_name, "JPEG")
    
    with open(workflowfile, 'r', encoding="utf-8") as workflow_api_txt2gif_file:
        
         # First upload Image to ComfyUI
        upload_image(input_image_name, filename, COMFYUI_ENDPOINT, overwrite=True)

        prompt_data = json.load(workflow_api_txt2gif_file)
        
        #set the text prompt for our positive CLIPTextEncode
        prompt_data["46"]["inputs"]["text"] = prompt

        # set the text prompt for the negative CLIPTextEncode
        prompt_data["47"]["inputs"]["text"] = negative_prompt

        #set the seed for our KSampler node
        prompt_data["45"]["inputs"]["noise_seed"] = seed

        #set the input portrait image
        prompt_data["53"]["inputs"]["image"] = filename
        
        return get_images(ws, prompt_data, input_image_name)

def queue_prompt(prompt):
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    req =  urllib.request.Request("http://{}/prompt".format(COMFYUI_ENDPOINT), data=data)
    
    return json.loads(urllib.request.urlopen(req).read())

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

 
def get_images(ws, prompt, input_image_name):
    prompt_id = queue_prompt(prompt)['prompt_id']
    # print(prompt_id)
    output_images = {}
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message['type'] == 'executing':
                data = message['data']
                if data['node'] is None and data['prompt_id'] == prompt_id:
                    break #Execution is done
        else:
            continue

    history = get_history(prompt_id)[prompt_id]
    # for hist_outs in history['outputs']:
    for node_id in history['outputs']:
        node_output = history['outputs'][node_id]
        # image branch
        if 'images' in node_output:
            images_output = []
            for image in node_output['images']:
                image_data = get_image(image['filename'], image['subfolder'], image['type'])
                images_output.append(image_data)
            output_images[node_id] = images_output
        # video branch
        if 'videos' in node_output:
            videos_output = []
            for video in node_output['videos']:
                video_data = get_image(video['filename'], video['subfolder'], video['type'])
                videos_output.append(video_data)
            output_images[node_id] = videos_output
    
    # do not persist input image
    os.remove(input_image_name)

    return output_images

def get_history(prompt_id):
    with urllib.request.urlopen("http://{}/history/{}".format(COMFYUI_ENDPOINT, prompt_id)) as response:
        return json.loads(response.read())

def get_image(filename, subfolder, folder_type):
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    with urllib.request.urlopen("http://{}/view?{}".format(COMFYUI_ENDPOINT, url_values)) as response:
        return response.read()

def describe_picture():
    if st.session_state.get("img_file_buffer") is not None:

        with Image.open(st.session_state.get("img_file_buffer")) as image:
            with io.BytesIO() as buf:
                image.save(buf, 'jpeg')
                image_bytes = buf.getvalue()
                encoded_image = base64.b64encode(image_bytes).decode('utf8')
                
        body = json.dumps( {"anthropic_version": "bedrock-2023-05-31", "max_tokens": 500,
                            "messages": [ { "role": "user", "content": [ {
                                        "type": "image", "source": { "type": "base64", "media_type": "image/jpeg", "data": encoded_image, }, },
                                        {"type": "text", "text": "What is in this image?"}, ], } ], }
        )
        # print("invoking!")
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
    st.header("",divider='rainbow')

    st.markdown(''' #### :information_source:   Disclaimer  
    - Uploaded user images are :green[deleted after the event]
    - Generated avatars are :green[only displayed in the gallery with consent (click on share avatar)]
    - The application is fully automated. We have included guardails in place to moderate unintented content
    - Powered by AWS Sample: [comfyui-personalized-generative-ai-avatars-app](https://github.com/aws-samples/comfyui-personalized-generative-ai-avatars-app)
    ''', unsafe_allow_html=True)
    
    if st.button("Logout"):
        logout()

    if 'filename' not in st.session_state:
        st.session_state['filename'] = None

    # Session state initialization for image buffer and control flags
    if 'img_file_buffer' not in st.session_state:
        st.session_state['img_file_buffer'] = None
    if 'capture' not in st.session_state:
        st.session_state['capture'] = True

    # Option for users to choose between webcam and file upload
    # option = st.radio("Choose your input method:",
    #                   ('Upload an Image', 'Capture from Webcam'))

    # if option == 'Capture from Webcam':
    #     if st.session_state['capture']:
    #         captured_image = st.camera_input("Take a picture using your webcam")
    #         if captured_image is not None:
    #             st.session_state['img_file_buffer'] = captured_image
    #             st.session_state['capture'] = False
    #             st.rerun()

    # elif option == 'Upload an Image':
    #     uploaded_file = st.file_uploader("Or upload a portrait image from your device:", type=['png', 'jpg', 'jpeg'])
    #     if uploaded_file is not None:
    #         st.session_state['img_file_buffer'] = uploaded_file

    if "file_uploader_key" not in st.session_state:
        st.session_state["file_uploader_key"] = 0

    st.header("",divider='rainbow')

    # check if Backend (ComfyUI) is available
    comfyui_backend = is_comfyui_running()
    if not comfyui_backend:
        st.warning("Backend (ComfyUI) is not available. Please check your ComfyUI configuration.")
    else:
        st.header("Upload or Capture an Image")
        uploaded_file = st.file_uploader("click on \"Browse files\"", type=['png', 'jpg', 'jpeg'], accept_multiple_files=False, key=st.session_state["file_uploader_key"])
        if uploaded_file is not None:
            if st.session_state.get('img_file_buffer') != uploaded_file:
                clear_session_state()
                st.session_state['img_file_buffer'] = uploaded_file
                st.session_state['filename'] = "photo-" + str(uuid.uuid4())[-17:] + ".png"
                
                # Preprocess and perform face detection
                processed_image = preprocess_image(st.session_state['img_file_buffer'], max_size=1024)
                if processed_image:
                    try:
                        rekog_portrait = RekognitionImage(Image.open(io.BytesIO(processed_image)), st.session_state["file_uploader_key"], client)
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
            input_image_name = local_path+"input/"+filename
            
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
                        negative_prompt_data= json.load(negative_prompt)

                    # Create a dictionary from the data for quick access
                    negative_prompt_dict = {item['negative_prompt']: item['prompt'] for item in negative_prompt_data}

                    # set negative prompt default
                    negative_prompt = negative_prompt_dict.get('default', '')

                    #st.session_state["seed"] = st.number_input("Random seed", min_value=1, max_value=int(1e9), value=st.session_state["seed"], step=1, format="%i")
                    seed = int(random.random()*1e8)
                
                    option = st.selectbox(
                        'Choose a preset style',
                        ['Sci-Fi', 'EURO 2024', 'Other Sports'])
                    
                    if "Sci-Fi" in option:
                        preset_options = [preset['Element_Preset'] for preset in scifi_presets]
                        index_option = round(st.session_state["rnd1"] / rnd1_max) % len(preset_options)

                        avatar_preset = st.radio("Presets",
                                    preset_options, 
                                    horizontal=True, 
                                    index=index_option,
                                    label_visibility="collapsed")
                        selected_preset = next((item for item in scifi_presets if item['Element_Preset'] == avatar_preset), None)
                        scifi_negative_prompt = negative_prompt_dict.get('scifi', '')

                    if "EURO 2024" in option:
                        preset_options = [preset['Club'] for preset in football_presets]
                        index_option = round(st.session_state["rnd1"] / rnd1_max) % len(preset_options)
                        avatar_preset = st.radio("Presets",
                                    preset_options, 
                                    horizontal=True, 
                                    index=index_option,
                                    label_visibility="collapsed")
                        
                        selected_preset = next((item for item in football_presets if item['Club'] == avatar_preset), None)
                        football_negative_prompt = negative_prompt_dict.get('football', '')

                    if "Other Sports" in option:
                        preset_options = [preset['Club'] for preset in sports_presets]
                        index_option = round(st.session_state["rnd1"] / rnd1_max) % len(preset_options)
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
                        ["Man", "Woman", "Nonbinary"], horizontal=True, index=round(st.session_state["rnd2"]/rnd2_max))
                    if avatar_gender == "Man":
                        preset_prompt = preset_prompt.replace("gender", "male")
                    elif avatar_gender == "Woman":
                        preset_prompt = preset_prompt.replace("gender", "female")
                    else:
                        preset_prompt = preset_prompt.replace("gender", "nonbinary gender")
                    
                    avatar_hair = st.radio("Hair length",
                        ["Short", "Medium", "Long", "No Hair"], horizontal=True, index=round(st.session_state["rnd3"]/rnd3_max))
                    
                    if avatar_hair == "No Hair":
                        avatar_hair_color = "no color"
                    else:
                        avatar_hair_color = st.radio("Hair color",
                            ["Blonde", "Brown", "Black", "Red", "Blue", "Green", "Purple", "Grey", "Random"], horizontal=True, index=round(st.session_state["rnd4"]/rnd4_max))
                
                    avatar_skin_tone = st.radio("Skin Tone",
                        ["Light", "Medium", "Dark"], horizontal=True, index=round(st.session_state["rnd7"]/rnd7_max))
                    
                    avatar_face_expr = st.radio("Facial Expression",
                        ["Serious", "Happy"], horizontal=True, index=round(st.session_state["rnd8"]/rnd8_max))
                    
                    if avatar_hair == "No Hair":
                        features = avatar_face_expr+" face, "+avatar_skin_tone+" skin tone, "+avatar_hair+", bald,  "
                    else:
                        features = avatar_face_expr+" face, "+avatar_skin_tone+" skin tone, "+avatar_hair+" "+avatar_hair_color+" hair, "
                    
                    preset_prompt = preset_prompt.replace("Features:", "Features: "+features)

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

                    if st.button('Create avatar', key="create_avatar", on_click=created_avatar, use_container_width=True):
                        # print(seed)
                        ws = websocket.WebSocket()
                        client_id = str(uuid.uuid4())
                        ws.connect("ws://{}/ws?clientId={}".format(COMFYUI_ENDPOINT, client_id))
                        images = parse_workflow(ws, prompt, negative_prompt, seed, input_image_name, filename)

                        st.session_state["avatar_final_image"] = ""
                        for node_id in images:
                            for image_output in images[node_id]:
                                image_data = Image.open(io.BytesIO(image_output))
                                st.session_state["avatar_final_image"] = image_data
                                if image_moderation:
                                    rekog_img = RekognitionImage(st.session_state["avatar_final_image"], st.session_state["glb_photo_name"], client)
                                    st.session_state["rekog_img_labels"] = rekog_img.detect_moderation_labels()
                                    print("Moderation labels detected: " + str(st.session_state["rekog_img_labels"]))
                    
                with col3:
                    st.header("Generated Avatar")
                    if st.session_state.get("avatar_final_image"):
                        print("image_moderation",image_moderation,"glb_photo_name",st.session_state["glb_photo_name"])
                        if st.session_state["glb_photo_name"] != 'placeholder':
                        
                        # Show Avatar
                            if len(st.session_state["rekog_img_labels"]) == 0:
                                st.session_state["displayed_avatar"] = st.image(st.session_state["avatar_final_image"], caption='Avatar', use_column_width="always", output_format="PNG" )
                                
                                # Share Avatar
                                if st.button('Share your avatar!', key="share_avatar", disabled= st.session_state["avatar_created"]):
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
