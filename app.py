from openai import OpenAI
import os
import streamlit as st
from datetime import datetime
import tempfile
import re
from docx import Document
from htmldocx import HtmlToDocx
import boto3
from botocore.exceptions import NoCredentialsError
import zipfile

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def upload_to_aws_s3(local_file, bucket, s3_file):
    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_BUCKET_REGION")
    )
    try:
        s3.upload_file(local_file, bucket, s3_file)
        print(f"Upload Successful: {s3_file}")
        return True
    except FileNotFoundError:
        print("The file was not found")
        return False
    except NoCredentialsError:
        print("Credentials not available")
        return False

from docx import Document
from htmldocx import HtmlToDocx

def html_to_docx(html_content, docx_filename):
    # Initialize a new Document object
    document = Document()
    parser = HtmlToDocx()
    # Instead of directly adding HTML to the document, we first check if the parser can be safely used
    try:
        parser.add_html_to_document(html_content, document)
    except AttributeError:
        # If an AttributeError occurs, log an error or handle it appropriately
        # For simplicity, we'll just print a message here but you might want to handle this more gracefully
        print(f"Failed to add HTML content to DOCX for {docx_filename} due to an unexpected error.")
    else:
        # If no error occurs, save the document
        document.save(docx_filename)
        print(f"DOCX file created and saved: {docx_filename}")

def sanitize_filename(filename):
    return "".join([c for c in filename if c.isalpha() or c.isdigit() or c in [' ', '_', '-']]).rstrip()

def create_zip_file(files, zip_filename):
    with zipfile.ZipFile(zip_filename, 'w') as zipf:
        for file in files:
            zipf.write(file, os.path.basename(file))
    print(f"ZIP file created and saved: {zip_filename}")

def generate_lesson_plans(number_of_lessons, unit_details):
    your_s3_bucket_name = os.getenv("S3_BUCKET_NAME")
    # Updated prompt to instruct the AI to use a single template repeatedly
    full_prompt = f"Generate {number_of_lessons} lesson plans for a unit based on the following details:\n{unit_details}\n\n" \
                    "Intelligently infer and fill in with content that logically fits such a unit and lessons. Ensure the unit and each lesson is comprehensive, covering necessary educational components, and ready for educational use. Be clear and explicit in all details." \
                    "For each lesson, use the following template and include a unique lesson number and title:\n" \
                    "---START LESSON---" \
                    "<h1>Unit Title: [Unit Title Here]</h1>"  \
                    "<h2>Written by: [Teacher Name]</h2>" \
                    "<h2>Lesson Number: [Unique Number]</h2>" \
                    "<h2>Lesson Title: [Title Here]</h2></ br>" \
                    "<H3>Objectives:</h3> <p>[Objectives Here]</p>" \
                    "<h3>Lesson Procedure:</h3> <ol>" \
                    "<li>Step 1: [Procedure Step 1]</li>" \
                    "<li>Step 2: [Procedure Step 2]</li>" \
                    "<li>Step 3: [Procedure Step 3]</li>" \
                    "</ol>" \
                    "<h3>Assessment and Evaluation:</h3> <p>[Assessment Here]</p>" \
                    "<h3>Materials Needed:</h3> <ul><li>[Material 1]</li><li>[Material 2]</li><li>[Etc...]</li></ul>" \
                    "<h3>Additional Resources:</h3> <ul><li>[Resource 1]</li><li>[Resource 2]</li><li>[Etc...]</li></ul>" \
                    "---END LESSON---<br><br>" \
                    "---UNIT SUMMARY---<br>" \
                    "<h1>[Unit Title]</h1>" \
                    "<h2>Unit Summary</h2>" \                    
                    "<h2>Written by: [Teacher Name]</h2>" \
                    "<h3>Unit Overview:</h3> <p>[Provide a brief overview of the unit, including the main themes and topics covered.]</p>" \
                    "<h3>Unit Objectives:</h3> <ul><li>[Objective 1]</li><li>[Objective 2]</li><li>[Etc...]</li></ul>" \
                    "<h3>Lesson Summaries:</h3> <ol>" \
                    "<li>Lesson 1: [Brief Summary]</li>" \
                    "<li>Lesson 2: [Brief Summary]</li>" \
                    "<li>Etc...</li>" \
                    "</ol>" \
                    "<h3>Materials Needed for the Unit:</h3> <ul><li>[Material 1]</li><li>[Material 2]</li><li>[Etc...]</li></ul>" \
                    "<h3>Additional Notes:</h3> <p>[Any other relevant information, notes for the teacher, or suggestions for extending the unit.]</p>" \
                    "[Include an overview of the unit, unit objectives, lesson summaries, materials needed, and other relevant info in this section.]"
    print("Sending the following prompt to OpenAI:\n", full_prompt)

    response = client.chat.completions.create(
        model="gpt-3.5-turbo-16k",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that can generate detailed lesson plans and unit summaries."},
            {"role": "user", "content": full_prompt},
        ],
        max_tokens=8000,
        n=1,
        stop=None,
        temperature=0.7
    )

    html_content = response.choices[0].message.content
    # Save the original prompt for reference
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as temp_prompt_file:
        temp_prompt_file.write(full_prompt)
    upload_to_aws_s3(temp_prompt_file.name, your_s3_bucket_name, f"prompts/{datetime.now().strftime('%Y%m%d_%H%M%S')}_prompt.txt")
    os.remove(temp_prompt_file.name)

    # Parse the response and generate DOCX files
    lesson_pattern = re.compile(r'---START LESSON---(.*?)---END LESSON---', re.DOTALL)
    summary_pattern = re.compile(r'---UNIT SUMMARY---(.*?)$', re.DOTALL)
    lesson_matches = lesson_pattern.findall(html_content)
    summary_match = summary_pattern.search(html_content)
    docx_files = []
    for i, lesson_content in enumerate(lesson_matches, start=1):
        docx_filename = f"Lesson - {i}.docx"
        html_to_docx(lesson_content, docx_filename)
        docx_files.append(docx_filename)
        print(f"Lesson {i} processed and DOCX created.")

    if summary_match:
        summary_content = summary_match.group(1)
        summary_filename = f"{unit_title} - Unit Summary.docx"
        html_to_docx(summary_content, summary_filename)
        docx_files.append(summary_filename)
        print("Unit summary processed and DOCX created.")

    # Create a ZIP file containing all DOCX files
    zip_filename = f"Lesson_Plans_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    create_zip_file(docx_files, zip_filename)

    # Upload ZIP file to AWS S3 and provide a download link
    upload_success = upload_to_aws_s3(zip_filename, your_s3_bucket_name, f"lesson_plans/{zip_filename}")
    if upload_success:
        download_link = f"https://{your_s3_bucket_name}.s3.amazonaws.com/lesson_plans/{zip_filename}"
        print(f"ZIP file uploaded successfully. Download link: {download_link}")
        return download_link
    else:
        print("Failed to upload ZIP file to AWS S3.")
        return "Failed to upload ZIP file to AWS S3."

# Streamlit UI for Input and Triggering the Process
st.title("Lesson Plan and Unit Summary Generator")
number_of_lessons = st.number_input("Number of Lessons:", min_value=1, max_value=8, value=1)
class_name = st.text_input("Class Name:")
teacher_name = st.text_area("Teacher Name:")
grade_level = st.text_input("Grade/Level:")
unit_title = st.text_input("Unit Title:")
objectives = st.text_area("Unit Objectives:")
standards = st.text_area("Standards:")
potential_lesson_titles = st.text_area("Potential Lesson Titles (separated by commas):")
general_notes = st.text_area("General Notes:")

unit_details = f"Class Name: {class_name}\Teacher Name: {teacher_name}\nGrade/Level: {grade_level}\nUnit Title: {unit_title}\nObjectives: {objectives}\nStandards: {standards}\nPotential Lesson Titles: {potential_lesson_titles}\nGeneral Notes: {general_notes}"

if st.button("Generate Lesson Plans and Unit Summary"):
    with st.spinner("Generating..."):
        download_link = generate_lesson_plans(number_of_lessons, unit_details)
        st.markdown(f'Download your lesson plans and unit summary: [Here]({download_link})')