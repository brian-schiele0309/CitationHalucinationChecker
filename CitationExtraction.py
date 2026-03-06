import json

##Open citation json file and extract relevant fields into a list of dictionaries
with open("GrobidTest/citations.json",'r') as file:
    citation_dict = json.load(file)

##Specify fields to extract from the citation json file
FIELDS = ['title', 'authors', 'publication_date', 'journal']


##Isolate references
refs = citation_dict['references']

##Extract relevant fields into a list of dictionaries
list_of_citations = []
for i in range(len(refs)):
    ref = refs[i]
    list_of_citations.append({})

    for field in FIELDS:
        if field in ref:
            list_of_citations[i][field] = ref[field]