from grobid_client.grobid_client import GrobidClient
import requests
import os
from pathlib import Path
import shutil
import json

##Download a papers pdf given a url
def download_pdf(url, filename="paper.pdf"):
    """
    Downloads a pds and stores it into a folder for Grobid extraction

    url: PDF URL
    Filename: What the file should be named
    """
    ##Creates Folder
    Path("Paper").mkdir(parents=True, exist_ok=True)


    response = requests.get(url)
    response.raise_for_status()

    storage_spot = os.path.join("Paper",filename)
    with open(storage_spot, "wb") as f:
        f.write(response.content)
    
    return storage_spot


##Extract citations using Grobid
def extractCitations():
    client = GrobidClient()


    client.process(
        service="processReferences",
        input_path="Paper",
        output="GrobidTest",
        n=20,
        json_output=True
    )
    
    shutil.rmtree("Paper")


##Download and extract
z = download_pdf("https://proceedings.neurips.cc/paper_files/paper/2023/file/aa5d22c77b380e2261332bb641b3c2e3-Paper-Conference.pdf", "citations.pdf")
extractCitations()
