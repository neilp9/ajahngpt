from django.shortcuts import render
from bs4 import BeautifulSoup
import os, re, urllib.parse
from .constants import ScrapingConstants
import requests
from datetime import datetime
import PyPDF2
from weasyprint import HTML

# Create your views here.


def _scrape_talks():
    '''
    Scrape from target site all documents

    Output format is list of dicts: {"title": "X", "location": url, "date": datetime}
    '''

    # download archive page
    response = requests.get(ScrapingConstants.ARCHIVE_URL)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'html.parser')

    # Extracting all links with class 'pdf' along with their titles and full dates
    docs = []
    for link in soup.find_all('a', class_='pdf'):
        # Find the title, excluding the smalldate (day of month)
        audio_link = link.find_previous_sibling('a', class_='audio')
        # get day of month
        dom = audio_link.find('span', class_='smalldate')
        if audio_link:
            title = ''.join(audio_link.stripped_strings)
            # Remove the smalldate part if it exists
            if dom:
                title = title.replace(dom.text, '').strip()
        else:
            print(f"found no title: {link}")
            title = 'UNTITLED'

        # Find the month and year
        month_year = link.find_previous('li', class_='month')
        dt = None
        if month_year:
            month_year_text = month_year.text.strip()
            month_year_match = re.search(r'(\w+)\s+(\d{4})', month_year_text)
            if month_year_match:
                month, year = month_year_match.groups()     
                try:
                    dt = datetime.strptime(f"{year} {month} {dom.text}", '%Y %B %d')
                except ValueError:
                    dt = datetime.strptime(f"{year} {month}", '%Y %B')
            else:
                print(f"unable to create full date: {link}")

        docs.append({'title': title, 'date': dt, 'url': link.get('href'), 'type': ScrapingConstants.FILE_TYPE_TALK})

    return docs

def _download(url, filename=None, destination_path='./'):
    '''
    Generic utility to download a file from a URL to a local filesystem destination
    '''
    if filename is None:
        filename = url.split('/')[-1]

    file_path = os.path.join(destination_path, filename)
    if not os.path.isfile(file_path):
        response = requests.get(url)
        response.raise_for_status()  # Check if the download was successful

        with open(file_path, 'wb') as file:
            file.write(response.content)
        print(f"downloaded {filename} to {file_path}")
        return filename
    
    

def _download_docs(docs, destination_path='./'):
    '''
    Take set of scraped doc locations and download the files to the given path

    Rename the documents based on title and date of talk
    '''
    download_count = 0
    for doc in docs:
        talk_date = doc['date'].strftime("%Y-%b-%d")
        extension = doc['url'][doc['url'].find('.'):]

        # Define the set of illegal characters for filenames (common to Windows and Unix systems)
        illegal_chars = r'[<>:"/\\|?*\x00-\x1F]'
        # Replace illegal characters with an underscore
        cleaned_title = re.sub(illegal_chars, '_', doc['title'])
        
        filename = f"{doc['type']}_{cleaned_title}_{talk_date}{extension}"
        downloaded = _download(urllib.parse.urljoin(ScrapingConstants.HOME_URL, doc['url']), filename, destination_path)
        if downloaded:
            download_count += 1

    print(f"downloaded {download_count} new files")


def _merge_pdfs(source_path, max_size_mb, destination_path, merge_to=None):
    def _convert_html_to_pdf(html_path, pdf_path):
        # Convert an HTML file to a PDF file
        if not os.path.isfile(pdf_path):
            print(f'converting HTML to PDF from {html_path} to {pdf_path}')
            HTML(html_path).write_pdf(pdf_path)
        else:
            print(f'converted file already exists:{pdf_path}')

    # Initialize list to hold the PDF writers
    pdf_writers = []

    # Initialize the current size
    current_size = 0

    # If a merge target is provided and exists
    if merge_to and os.path.exists(merge_to):
        with open(merge_to, 'rb') as merge_file:
            writer = PyPDF2.PdfWriter()
            reader = PyPDF2.PdfReader(merge_file)
            for page_num in range(len(reader.pages)):
                writer.addPage(reader.pages[page_num])
            pdf_writers.append(writer)
            current_size += os.path.getsize(merge_to)
    else:
        pdf_writers.append(PyPDF2.PdfWriter())

    # Iterate over all files in the source folder
    for filename in sorted(os.listdir(source_path)):
        file_path = os.path.join(source_path, filename)
        
        # Convert HTML files to PDF
        if filename.endswith('.html'):
            pdf_path = os.path.join(source_path, filename + '.pdf')
            _convert_html_to_pdf(file_path, pdf_path)
            file_path = pdf_path

        # Process PDF files
        if file_path.endswith('.pdf') and (merge_to is None or filename != os.path.basename(merge_to)):
            # Open the PDF file
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                num_pages = len(reader.pages)

                # Create a new writer if the current one is full
                if current_size + os.path.getsize(file_path) > max_size_mb * 1024 * 1024 * 5:
                    pdf_writers.append(PyPDF2.PdfWriter())
                    current_size = 0

                # Add pages to the latest writer
                for page_num in range(num_pages):
                    pdf_writers[-1].add_page(reader.pages[page_num])
                    current_size += os.path.getsize(file_path)

    # Ensure the destination directory exists
    if not os.path.exists(destination_path):
        os.makedirs(destination_path)

    # Save the merged PDFs in the destination folder
    for i, writer in enumerate(pdf_writers):
        # find a unique filename
        while True:
            output_filename = os.path.join(destination_path, f'merged_{i+1}.pdf')
            if not os.path.isfile(output_filename):
                break
            i += 1
            
        with open(output_filename, 'wb') as output_file:
            writer.write(output_file)
            print(f'saved {output_filename}')