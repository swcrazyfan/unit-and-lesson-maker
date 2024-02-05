from openai import OpenAI
import os
import streamlit as st
from datetime import datetime
import tempfile
import random
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

def html_to_docx(html_content, docx_filename):
    document = Document()
    parser = HtmlToDocx()
    parser.add_html_to_document(html_content, document)
    document.save(docx_filename)

def sanitize_filename(filename):
    return "".join([c for c in filename if c.isalpha() or c.isdigit() or c in [' ', '_', '-']]).rstrip()

def create_zip_file(files, zip_filename):
    with zipfile.ZipFile(zip_filename, 'w') as zipf:
        for file in files:
            zipf.write(file, os.path.basename(file))

def generate_lesson_plans(number_of_lessons, unit_details):
    your_s3_bucket_name = os.getenv("S3_BUCKET_NAME")
    lesson_plan_template = """
    ---START [Lesson Title {lesson_number}]---
    <h1>Lesson {lesson_number}: [Lesson Title Here]</h1>
    <h2>Objectives</h2>
    <p>[Objectives Here]</p>
    <h2>Materials Needed</h2>
    <p>[Materials Here]</p>
    <h2>Lesson Procedure</h2>
    <p>[Procedure Here]</p>
    <h2>Assessment and Evaluation</h2>
    <p>[Assessment Here]</p>
    <h2>Additional Resources</h2>
    <p>[Resources Here]</p>
    ---END [Lesson Title {lesson_number}]---
    """
    full_prompt = "Generate a unit consisting of {number_of_lessons} lesson plans based on the following details:\n{unit_details}\n\n".format(number_of_lessons=number_of_lessons, unit_details=unit_details)
    for i in range(1, number_of_lessons + 1):
        full_prompt += lesson_plan_template.format(lesson_number=i)
    full_prompt += "\n---UNIT SUMMARY---\n[At the end, include an overview of the unit, unit objectives, lesson summaries, materials needed, and other relevant info in this section.]"

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
    lesson_pattern = re.compile(r'---START \[Lesson Title (\d+)\]---(.*?)---END \[Lesson Title \1\]---', re.DOTALL)
    summary_pattern = re.compile(r'---UNIT SUMMARY---(.*?)$', re.DOTALL)
    lesson_matches = lesson_pattern.findall(html_content)
    summary_match = summary_pattern.search(html_content)
    docx_files = []
    for match in lesson_matches:
        lesson_number, lesson_content = match
        docx_filename = f"Lesson_{lesson_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        html_to_docx(lesson_content, docx_filename)
        docx_files.append(docx_filename)

    if summary_match:
        summary_content = summary_match.group(1)
        summary_filename = f"Unit_Summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        html_to_docx(summary_content, summary_filename)
        docx_files.append(summary_filename)

    # Create a ZIP file containing all DOCX files
    zip_filename = f"Lesson_Plans_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    create_zip_file(docx_files, zip_filename)

    # Upload ZIP file to AWS S3 and provide a download link
    upload_success = upload_to_aws_s3(zip_filename, your_s3_bucket_name, f"lesson_plans/{zip_filename}")
    if upload_success:
        return f"https://{your_s3_bucket_name}.s3.amazonaws.com/lesson_plans/{zip_filename}"
    else:
        return "Failed to upload ZIP file to AWS S3."

# Streamlit UI for Input and Triggering the Process
st.title("Lesson Plan and Unit Summary Generator")
number_of_lessons = st.number_input("Number of Lessons:", min_value=1, max_value=8, value=1)
class_name = st.text_input("Class Name:")
grade_level = st.text_input("Grade/Level:")
unit_title = st.text_input("Unit Title:")
objectives = st.text_area("Unit Objectives:")
standards = st.text_area("Standards:")
potential_lesson_titles = st.text_area("Potential Lesson Titles (separated by commas):")
general_notes = st.text_area("General Notes:")
unit_details = f"Class Name: {class_name}\nGrade/Level: {grade_level}\nUnit Title: {unit_title}\nObjectives: {objectives}\nStandards: {standards}\nPotential Lesson Titles: {potential_lesson_titles}\nGeneral Notes: {general_notes}"

if st.button("Generate Lesson Plans and Unit Summary"):
    with st.spinner("Generating..."):
        download_link = generate_lesson_plans(number_of_lessons, unit_details)
        st.markdown(f'Download your lesson plans and unit summary: [Here]({download_link})')