# Import dependencies    
import datetime    
import json    
import time    
import os    
import shutil
from openai import AzureOpenAI    
from dotenv import load_dotenv    
import copy    
import textwrap    
import requests    
import threading    
import streamlit as st    
from queue import Queue  
from PIL import Image
import base64
import io
import fitz  # PyMuPDF
import pandas as pd
from random import randint
from process_inputs import process_inputs  
# Load environment variables    
load_dotenv("./.env")    

# Define a flag to toggle deletion of the temporary folder
DELETE_TEMP_FOLDER = os.getenv("DELETE_TEMP_FOLDER", "true").lower() == "true"
TEMP_FOLDER = "./use-cases/Custom Scenario/images"

import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Get the value of the 'debug_mode' environment variable, default to 'true' if not set
offline_mode = os.getenv('offline_mode', 'true')
# Print the value
print(f"offline_mode: {offline_mode}")
# Log the value
logging.info(f"offline_mode: {offline_mode}")


offline_message="此功能在离线模式下被禁用。请在本地托管此应用程序并使用您自己的 API 密钥进行实时尝试！联系 luca.stamatescu@microsoft.com 了解更多信息。"

# Function to read XML file content as a string  
def load_use_case_from_file(file_path):  
    with open(file_path, 'r') as file:  
        return file.read()  
    
def get_csv_data(use_case,column_name):
    # Load the CSV file into a DataFrame
    csv_file_path = './o1-vs-4o-scenarios.csv'
    df = pd.read_csv(csv_file_path, encoding='utf-8-sig')
    row = df[df['Use Case'] == use_case]
    if not row.empty:
        return row.iloc[0][column_name]
    else:
        return f"Error - {column_name} not found."

def save_csv_data(use_case, column_name, value):
    # Check if debug_mode is true
    if os.getenv('debug_mode') == 'true':
        # Load the CSV file into a DataFrame
        csv_file_path = './o1-vs-4o-scenarios.csv'
        df = pd.read_csv(csv_file_path)
        
        # Check if the use case already exists
        if use_case in df['Use Case'].values:
            df.loc[df['Use Case'] == use_case, column_name] = value
            # Save the updated DataFrame back to the CSV file
            df.to_csv(csv_file_path, index=False, encoding='utf-8-sig')
        else:
            return f"Error - Use case '{use_case}' not found."


# Define function for calling GPT4o with streaming  
def gpt4o_call(system_message, user_message, result_dict, queue, selected_use_case):    
    if offline_mode == 'true':
        response_text = get_csv_data(selected_use_case, 'gpt4o')
        for i in range(0, len(response_text), 50):  # Simulate streaming
            queue.put(response_text[:i+50])
            time.sleep(0.2)
        result_dict['4o'] = {
            'response': response_text,
            'time': get_csv_data(selected_use_case, 'gpt4o_time')
        }
    else:
        client = AzureOpenAI(    
            api_version=os.getenv("4oAPI_VERSION"),    
            azure_endpoint=os.getenv("4oAZURE_ENDPOINT"),    
            api_key=os.getenv("4oAPI_KEY")    
        )    
        
        start_time = time.time()    
        
        completion = client.chat.completions.create(    
            model=os.getenv("4oMODEL"),    
            messages=[    
                {"role": "system", "content": system_message},    
                {"role": "user", "content": user_message},    
            ],    
            stream=True  # Enable streaming  
        )    
        
        response_text = ""  
        for chunk in completion:  
            if chunk.choices and chunk.choices[0].delta.content:  
                response_text += chunk.choices[0].delta.content  
                queue.put(response_text)  
        
        elapsed_time = time.time() - start_time    
        
        result_dict['4o'] = {    
            'response': response_text,    
            'time': elapsed_time    
        }    
        queue.put(f"Elapsed time: {elapsed_time:.2f} seconds")    

def o1_call(system_message, user_message):
    client = AzureOpenAI(    
        api_version=os.getenv("o1API_VERSION"),    
        azure_endpoint=os.getenv("o1AZURE_ENDPOINT"),    
        api_key=os.getenv("o1API_KEY")    
    )    
    
    start_time = time.time()    
    
    prompt = system_message + user_message

    completion = client.chat.completions.create(    
        model=os.getenv("o1API_MODEL"),    
        messages=[      
            {"role": "user", "content": prompt},    
        ],    
    )
    elapsed_time = time.time() - start_time   
    messageo1=completion.choices[0].message.content 
    return messageo1, elapsed_time  

# Define function for calling O1 and storing the result  
def o1_call_simultaneous_handler(system_message, user_message, result_dict,selected_use_case ):    
    if offline_mode == 'true':
        response = get_csv_data(selected_use_case, 'o1')
        # Sleep for the time taken by o1
        o1_time_elapsed = get_csv_data(selected_use_case, 'o1_time')
        time.sleep(o1_time_elapsed)
        print("SLEPT FOR ", o1_time_elapsed)
        result_dict['o1'] = {
            'response': response,
            'time': get_csv_data(selected_use_case, 'o1_time')
        }
    else:
        response,elapsed_time=o1_call(system_message, user_message)
        
        result_dict['o1'] = {    
            'response': response,    
            'time': elapsed_time    
        }    
  
# Define function for comparing responses using O1  
def compare_responses(response_4o, response_o1):  
    system_message = "You are an expert reviewer, who is helping review two candidates responses to a question."  
    user_message = f"Compare the following two responses and summarize the key differences:\n\nResponse 1 GPT-4o Model:\n{response_4o}\n\nResponse 2 o1 Model:\n{response_o1}. Generate a succinct comparison, and call out the key elements that make one response better than another. Be critical in your analysis."  
    comparison_result, _ = o1_call(system_message, user_message)  
      
    return comparison_result  

# Define function for comparing responses using O1  
def compare_responses_simple(response_4o, response_o1):  
    system_message = "You are an expert reviewer, who is helping review two candidates responses to a question."  
    user_message = f"Compare the following two responses and summarize the key differences:\n\nResponse 1 GPT-4o Model:\n{response_4o}\n\nResponse 2 o1 Model:\n{response_o1}. Generate a succinct comparison, and call out the key elements that make one response better than another. Be succinct- only use 3 sentences."  
    comparison_result, _ = o1_call(system_message, user_message)  
      
    return comparison_result  

# Function to process images and convert them to text using GPT-4o
def process_images(images):
    client = AzureOpenAI(
        api_version=os.getenv("4oAPI_VERSION"),
        azure_endpoint=os.getenv("4oAZURE_ENDPOINT"),
        api_key=os.getenv("4oAPI_KEY")
    )

    descriptions = []
    for image in images:
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode()

        system_prompt = "Generate a highly detailed text description of this image, making sure to capture all the information within the image as words. If there is text, tables or other text based information, include this in a section of your response as markdown."
        response = client.chat.completions.create(
            model=os.getenv("4oMODEL"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": "Here is the input image:"},
                    {"type": "image_url", "image_url": {"url": f'data:image/jpg;base64,{img_str}', "detail": "low"}}
                ]}
            ],
            temperature=0,
        )
        descriptions.append(response.choices[0].message.content)
    
    return descriptions

def process_pdf(pdf_path, output_folder):
    pdf_document = fitz.open(pdf_path)
    for page_num in range(len(pdf_document)):
        page = pdf_document.load_page(page_num)
        pix = page.get_pixmap()
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        image_path = os.path.join(output_folder, f"{os.path.splitext(os.path.basename(pdf_path))[0]}_page_{page_num + 1}.jepg")
        img.save(image_path, "JPEG")

def load_images_and_descriptions(selected_title):
    use_case_folder = f"./use-cases/{selected_title}/images"

    if os.path.exists(use_case_folder):
        image_files = [os.path.join(use_case_folder, f) for f in os.listdir(use_case_folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        descriptions = []
        for img_file in image_files:
            base_name = os.path.splitext(os.path.basename(img_file))[0]
            description_path = os.path.join(use_case_folder, f"{base_name}.txt")
            if os.path.exists(description_path):
                with open(description_path, 'r', encoding='utf-8') as f:
                    description = f.read()
                    descriptions.append((img_file, description))
    else:
        image_files = []
        descriptions = []

    if descriptions:
        st.session_state['descriptions'] = descriptions
    else:
        st.session_state['descriptions'] = []

# Streamlit app    
def main():

    def render_images_and_descriptions():  
        cols = st.columns(3)  # Adjust the number of columns as needed  
        fixed_height = 200  # Fixed height for images in pixels  
    
        for i, (img_path, description) in enumerate(st.session_state['descriptions']):  
            image = Image.open(img_path)  
            col = cols[i % 3]  
            with col.container():  
                buffered = io.BytesIO()  
                image.save(buffered, format="JPEG")  
                img_str = base64.b64encode(buffered.getvalue()).decode()  
                # Generate a unique key based on description content  
                unique_id = f"{i}"  
                col.markdown(  
                    f"""  
                    <style>  
                        .image-container-{unique_id} {{  
                            height: {fixed_height}px;  
                            display: flex;  
                            align-items: center;  
                            justify-content: center;  
                            overflow: hidden;  
                            margin-bottom: 5px;  
                        }}  
                        .image-container-{unique_id} img {{  
                            height: 100%;  
                            width: auto;  
                            object-fit: cover;  
                        }}  
                    </style>  
                    <div class='image-container-{unique_id}'>  
                        <img src='data:image/jpeg;base64,{img_str}' alt='Image'>  
                    </div>  
                    """,  
                    unsafe_allow_html=True  
                )  
                # Use st.text_area for the description with a unique key  
                col.text_area("Description", description, height=100, key=f"description_{i}")  

    st.set_page_config(page_title="Azure OpenAI Studio 实验室 | GPT-4o 与 4o 比较工具",page_icon="./favicon.ico", layout="wide")
    selected_item = st.sidebar.empty()

    def set_selected_item(item):
        st.session_state.selected_title = item
        load_images_and_descriptions(item)

    # Create two columns
    col1, col2 = st.sidebar.columns([8, 3])  # Adjust the ratio as needed

    # Place the title in the first column
    with col1:
        st.title("Azure OpenAI 实验室 🔬")

    # Place the image in the second column
    with col2:
        st.text("")
        st.text("")
        st.image("./azureopenaistudio.png", width=50)
 
    st.sidebar.subheader("GPT-4o 与 o1-preview 比较工具") 

    st.sidebar.markdown("---")  

    # Custom CSS to make buttons full width and prevent wrapping
    st.sidebar.markdown("""
        <style>
        .stButton button {
            width: 100%;
            white-space: nowrap;
        }
        </style>
    """, unsafe_allow_html=True)

    # # Hidden text input to store the selected item
    # st.sidebar.text_input("", key="selected_item", on_change=lambda: set_selected_item(st.session_state.selected_item))
    if st.sidebar.button("Custom Scenario", key="custom_1"):
        if offline_mode == 'true':
            st.toast(offline_message, icon="⚠️")
        else:
            set_selected_item("Custom Scenario")
            print(offline_mode)
    st.sidebar.markdown("---") 
    

    
    
    # Insurance section
    st.sidebar.header("保险")  
    if st.sidebar.button("家庭保险索赔 ⭐️", key="insurance_1"):
        # set_selected_item("家庭保险索赔")
        set_selected_item("Home Insurance Claim")
    if st.sidebar.button("汽车保险索赔 ⭐️", key="insurance_2"):
        # set_selected_item("汽车保险索赔")
        set_selected_item("Auto Insurance Claim")
    if st.sidebar.button("客户服务和保留", key="insurance_3"):
        # set_selected_item("客户服务和保留")
        set_selected_item("Customer Service and Retention")
    if st.sidebar.button("产品开发和创新", key="insurance_4"):
        # set_selected_item("产品开发和创新")
        set_selected_item("Product Development and Innovation")
    if st.sidebar.button("风险管理和合规", key="insurance_5"):
        # set_selected_item("风险管理和合规")
        set_selected_item("Risk Management and Compliance")
    st.sidebar.markdown("---")  

    # Banking section
    st.sidebar.header("银行")  
    if st.sidebar.button("信用风险评估和管理 ⭐️", key="banking_1"):
        # set_selected_item("信用风险评估和管理")
        set_selected_item("Credit Risk Assessment and Management")
    if st.sidebar.button("欺诈检测和预防", key="banking_2"):
        # set_selected_item("欺诈检测和预防")
        set_selected_item("Fraud Detection and Prevention")
    if st.sidebar.button("合规和报告", key="banking_3"):
        # set_selected_item("合规和报告")
        set_selected_item("Regulatory Compliance and Reporting")
    if st.sidebar.button("客户关系管理", key="banking_4"):
        # set_selected_item("客户关系管理")
        set_selected_item("Customer Relationship Management")
    if st.sidebar.button("投资和投资组合管理", key="banking_5"):
        # set_selected_item("投资和投资组合管理")
        set_selected_item("Investment and Portfolio Management")
    st.sidebar.markdown("---") 

    # Retail section
    st.sidebar.header("零售")  
    if st.sidebar.button("库存和供应链管理", key="retail_1"):
        # set_selected_item("库存和供应链管理")
        set_selected_item("Inventory and Supply Chain Management")
    if st.sidebar.button("商品和定价", key="retail_2"):
        # set_selected_item("商品和定价")
        set_selected_item("Merchandising and Pricing")
    if st.sidebar.button("客户细分和个性化", key="retail_3"):
        # set_selected_item("客户细分和个性化")
        set_selected_item("Customer Segmentation and Personalization")
    if st.sidebar.button("全渠道和电子商务", key="retail_4"):
        # set_selected_item("全渠道和电子商务")
        set_selected_item("Omnichannel and E-commerce")
    if st.sidebar.button("忠诚度和保留", key="retail_5"):
        # set_selected_item("忠诚度和保留")
        set_selected_item("Loyalty and Retention")
    st.sidebar.markdown("---")  



    # Utilities section
    st.sidebar.header("公用事业")  
    if st.sidebar.button("需求和供应管理", key="utilities_1"):
        # set_selected_item("需求和供应管理")
        set_selected_item("Demand and Supply Management")
    if st.sidebar.button("资产和网络管理", key="utilities_2"):
        # set_selected_item("资产和网络管理")
        set_selected_item("Asset and Network Management")
    if st.sidebar.button("客户服务和计费", key="utilities_3"):
        # set_selected_item("客户服务和计费")
        set_selected_item("Customer Service and Billing")
    if st.sidebar.button("能源效率和可持续性", key="utilities_4"):
        # set_selected_item("能源效率和可持续性")
        set_selected_item("Energy Efficiency and Sustainability")
    if st.sidebar.button("合规和报告", key="utilities_5"):
        # set_selected_item("合规和报告")
        set_selected_item("Regulatory Compliance and Reporting")
    st.sidebar.markdown("---")  

    # Mining section
    st.sidebar.header("采矿")  
    if st.sidebar.button("勘探和可行性", key="mining_1"):
        # set_selected_item("勘探和可行性")
        set_selected_item("Exploration and Feasibility")
    if st.sidebar.button("矿山规划和设计", key="mining_2"):
        # set_selected_item("矿山规划和设计")
        set_selected_item("Mine Planning and Design")
    if st.sidebar.button("生产和加工", key="mining_3"):
        # set_selected_item("生产和加工")
        set_selected_item("Production and Processing")
    if st.sidebar.button("环境和社会影响", key="mining_4"):
        # set_selected_item("环境和社会影响")
        set_selected_item("Environmental and Social Impact")
    if st.sidebar.button("健康和安全", key="mining_5"):
        # set_selected_item("健康和安全")
        set_selected_item("Health and Safety")
    st.sidebar.markdown("---")  

    # Telecommunications section
    st.sidebar.header("电信")  
    if st.sidebar.button("网络规划和优化", key="telecom_1"):
        # set_selected_item("网络规划和优化")
        set_selected_item("Network Planning and Optimization")
    if st.sidebar.button("服务开发和创新", key="telecom_2"):
        # set_selected_item("服务开发和创新")
        set_selected_item("Service Development and Innovation")
    if st.sidebar.button("客户获取和保留", key="telecom_3"):
        # set_selected_item("客户获取和保留")
        set_selected_item("Customer Acquisition and Retention")
    if st.sidebar.button("计费和收入管理", key="telecom_4"):
        # set_selected_item("计费和收入管理")
        set_selected_item("Billing and Revenue Management")
    if st.sidebar.button("合规和报告", key="telecom_5"):
        # set_selected_item("合规和报告")
        set_selected_item("Regulatory Compliance and Reporting")
    st.sidebar.markdown("---")  

    # Healthcare section
    st.sidebar.header("医疗保健")  
    if st.sidebar.button("诊断和治疗", key="healthcare_1"):
        # set_selected_item("诊断和治疗")
        set_selected_item("Diagnosis and Treatment")
    if st.sidebar.button("护理协调和管理", key="healthcare_2"):
        # set_selected_item("护理协调和管理")
        set_selected_item("Care Coordination and Management")
    if st.sidebar.button("疾病预防和健康促进", key="healthcare_3"):
        # set_selected_item("疾病预防和健康促进")
        set_selected_item("Disease Prevention and Health Promotion")
    if st.sidebar.button("研究和创新", key="healthcare_4"):
        # set_selected_item("研究和创新")
        set_selected_item("Research and Innovation")
    if st.sidebar.button("合规和报告", key="healthcare_5"):
        # set_selected_item("合规和报告")
        set_selected_item("Compliance and Reporting")
    st.sidebar.markdown("---")  

    # Education section
    st.sidebar.header("教育")  
    if st.sidebar.button("课程设计和交付", key="education_1"):
        # set_selected_item("课程设计和交付")
        set_selected_item("Curriculum Design and Delivery")
    if st.sidebar.button("评估和评价", key="education_2"):
        # set_selected_item("评估和评价")
        set_selected_item("Assessment and Evaluation")
    if st.sidebar.button("学生支持和参与", key="education_3"):
        # set_selected_item("学生支持和参与")
        set_selected_item("Student Support and Engagement")
    if st.sidebar.button("专业发展和协作", key="education_4"):
        # set_selected_item("专业发展和协作")
        set_selected_item("Professional Development and Collaboration")
    if st.sidebar.button("管理和管理", key="education_5"):
        set_selected_item("Administration and Management")
        # set_selected_item("管理和管理")
    st.sidebar.markdown("---")  

    
    if 'selected_title' not in st.session_state or not st.session_state['selected_title']:
        st.markdown("### 概述")
        st.markdown("此工具旨在帮助您探索 OpenAI 的 o1-preview 模型和 GPT-4o 模型之间的差异。o1 是一种新型模型，能够为 LLM 解锁高级推理能力。通过在前期花费更多时间思考问题，o1 考虑了一系列边缘情况和潜在情况，从而得出更好的结论。这是以延迟为代价的。\n o1 有望改变许多行业，此工具旨在让您探索这些行业。")
        st.markdown("### 使用说明")
        st.markdown("点击左侧的场景以开始。您还可以通过选择“自定义场景”来上传您自己的场景。")
        if offline_mode=='true':
            st.markdown("### ⚠️离线模式⚠️")
            st.markdown("此工具当前在离线模式下运行。您仍然可以探索和运行所有场景，展示 GPT-4o 和 o1 的行为。但是，您将无法修改提示、上传文件或添加您自己的自定义场景。要实时尝试，请在本地托管此应用程序并使用您自己的 API 密钥。联系 Luca.Stamatescu@microsoft.com 了解更多信息。")
        st.markdown("### 归属")
        st.markdown("请联系 Luca Stamatescu 以获取有关此演示的更多信息。感谢 Salim Naim 开发提示策略和 Ibrahim Hamza 提供行业场景和用例。")
    else:
        # Main content
        st.title(st.session_state.get("selected_title", "Custom Scenario"))




        # Custom CSS to hide Streamlit header and footer and adjust padding
        hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .css-18e3th9 {padding-top: 0;}
            .css-1d391kg {padding-top: 0;}
            </style>
        """
        st.markdown(hide_streamlit_style, unsafe_allow_html=True)

        
        # Retrieve the selected use case from session state
        selected_use_case = st.session_state.get("selected_title", "Custom Scenario")



        st.markdown("##### 高级概述")
        overview = get_csv_data(selected_use_case,"Overview")

        st.markdown(overview)


        st.markdown("##### 详细分析")
        # Get the default input based on the selected use case
        default_input = get_csv_data(selected_use_case,"Prompt")

        # Input box (takes up the width of the screen)   
        #  
        user_input = st.text_area("", value=default_input, height=200)    

        # Section to upload supporting documents
        st.markdown("##### 上传支持文档")
        
        # Use session state to store uploaded files and the uploader key
        if 'uploaded_files' not in st.session_state:
            st.session_state.uploaded_files = None
        if 'uploader_key' not in st.session_state:
            st.session_state.uploader_key = str(randint(1000, 100000000))
        
        # File uploader with a unique key
        uploaded_files = st.file_uploader("选择图像或 PDF", accept_multiple_files=True, type=["jpeg", "pdf"])
        
        # Button to delete uploaded files
        if st.button("删除上传的文件"):
            if offline_mode == 'true':
                st.toast(offline_message, icon="⚠️")
            else:
                if DELETE_TEMP_FOLDER and os.path.exists(TEMP_FOLDER):
                    shutil.rmtree(TEMP_FOLDER)  
                    st.session_state.descriptions=None
            

        # Process uploaded files
        if uploaded_files and st.button("上传文件"):
            if offline_mode == 'true':
                st.toast(offline_message, icon="⚠️")
            else:
                process_inputs(uploaded_files)
                load_images_and_descriptions("Custom Scenario")
    
        # Display images as tiles with descriptions  
        if 'descriptions' in st.session_state and st.session_state.descriptions!=None:
            # Call the function to render images and descriptions
            render_images_and_descriptions()
    
        # Add a checkbox to toggle the comparison
        compare_models = st.checkbox("仅显示 o1-preview 输出", value=False)
      
        # Button to submit    
        if st.button("Submit"): 
            with st.spinner('处理中...'):
                if st.session_state['descriptions']:  
                    # Ensure descriptions is a string
                    concatenated_descriptions=""
                    descriptions = st.session_state['descriptions']
                    if isinstance(descriptions, list):
                        for description in descriptions:
                            concatenated_descriptions=concatenated_descriptions+description[1]
                    st.session_state['prompt'] = user_input + "\n\n" + concatenated_descriptions
                else:  
                    st.session_state['prompt'] = user_input

                # Conditionally display columns based on the checkbox state
                if not compare_models:
                    col1, col2 = st.columns(2)    
                else:
                    col2 = st.container()
                
                if not compare_models:
                    with col1:    
                        st.subheader("4o 响应")
                        st.markdown("---")
                        response_placeholder_4o = st.empty()  
                        st.markdown("---")
                        st.markdown("##### 时间")    
                        time_placeholder_4o = st.markdown("处理中...")   
        
                with col2:    
                    st.subheader("o1-preview 响应")   
                    st.markdown("---")
                    response_placeholder_o1 = st.empty() 
                    st.markdown("---")
                    st.markdown("##### 时间")   
                    time_placeholder_o1 = st.markdown("处理中...")   
                
                # Dictionary to store results    
                result_dict = {}    
                queue = Queue()  
                
                # Start threads for both API calls    
                threads = []    
                t1 = threading.Thread(target=gpt4o_call, args=("You are a helpful AI assistant.", st.session_state['prompt'], result_dict, queue,selected_use_case))    
                t2 = threading.Thread(target=o1_call_simultaneous_handler, args=("You are a helpful AI assistant.", st.session_state['prompt'], result_dict,selected_use_case))    
                threads.append(t1)    
                threads.append(t2)    
                t1.start()    
                t2.start()    
                
                if not compare_models:
                    # Update the Streamlit UI with the streamed response  
                    while t1.is_alive():  
                        while not queue.empty():  
                            response_placeholder_4o.write(queue.get())  
                        time.sleep(0.1)  
                
                # Wait for both threads to complete    
                for t in threads:    
                    t.join()    
                
                # Display the 4o response and elapsed time  
                if not compare_models:
                    with col1:
                        response_placeholder_4o.write(result_dict['4o']['response'])  
                        time_placeholder_4o.write(f"耗时: {result_dict['4o']['time']:.2f} 秒")  
                        if os.getenv('debug_mode') == 'true':
                            save_csv_data(selected_use_case, "gpt4o_time", float(round(result_dict['4o']['time'],2)))
                            save_csv_data(selected_use_case, "gpt4o", result_dict['4o']['response'])


                # Display the O1 response and elapsed time    
                with col2:    
                    response_placeholder_o1.write(result_dict['o1']['response'])   
                    time_placeholder_o1.write(f"耗时: {result_dict['o1']['time']:.2f} 秒")    
                    if os.getenv('debug_mode') == 'true':
                        save_csv_data(selected_use_case, "o1_time", float(round(result_dict['o1']['time'],2)))
                        save_csv_data(selected_use_case, "o1", result_dict['o1']['response'])

            if not compare_models:
                st.markdown("---")
                # Compare the responses and display the comparison  
                st.subheader("响应比较 - 概述")  

                with st.spinner('处理中...'):
                    if offline_mode == 'true':
                        comparison_result = get_csv_data(selected_use_case, 'simple_comparison')
                        # Simulate a wait time
                        time.sleep(15)
                    else:
                        comparison_result = compare_responses_simple(result_dict['4o']['response'], result_dict['o1']['response'])  
                    st.write(comparison_result)
                    save_csv_data(selected_use_case, "simple_comparison", comparison_result)

                st.markdown("---")
                # Compare the responses and display the comparison  
                st.subheader("响应比较 - 详细")  

                with st.spinner('Processing...'):
                    if offline_mode == 'true':
                        comparison_result = get_csv_data(selected_use_case, 'complex_comparison')
                        # Simulate a wait time
                        time.sleep(15)
                    else:
                        comparison_result = compare_responses(result_dict['4o']['response'], result_dict['o1']['response'])  
                    st.write(comparison_result)
                    save_csv_data(selected_use_case, "complex_comparison", comparison_result)



if __name__ == "__main__":
    main()
