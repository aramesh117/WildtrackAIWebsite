#------------------------------------------------------------------------
# Miscellaneous utilities for WIldTrack data/ image access & manipulation
#
# Author: D'Souza
##################################################
import dns
import pymongo
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient, __version__
from bson.objectid import ObjectId

MONGO_DB='wildtrack-db01'
AZURE_CONNECT_STRING = 'DefaultEndpointsProtocol=https;AccountName=wtimages01;AccountKey=k3BuXSlMiDyv+7ftWQqAPLKhu1OwIvd8W2/EjEjzVf/D/uSodDmCHp46KnGBFIaEBFpGHKdf5Jn9dxMkSWNqTQ==;EndpointSuffix=core.windows.net'
AZURE_BLOB_CONTAINER = "wtimages01-prod01"
AZURE_TEXT_CONTAINER = "wtimages-1-prod02"

#JTD+1 12/2020 Non longer needed
client = pymongo.MongoClient("mongodb+srv://mongoadmin:BmmfKb1UkIFbRFl5@cluster0.ybns4.azure.mongodb.net/admin?retryWrites=true&w=majority")
#client = pymongo.MongoClient("mongodb+srv://wildtrackdev:wildtrackai2020!@cluster0-abxwt.azure.mongodb.net/admin?retryWrites=true&w=majority")
db = client[MONGO_DB]
colsightings= db["Sightings"]
colartifacts= db["Artifacts"]
colfeedback=db["Feedback"]
colmodelsummaries=db["ModelSummaries"]
colspecies=db["Species"]

blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECT_STRING)
container_client = blob_service_client.get_container_client(AZURE_BLOB_CONTAINER)

def del_sighting(ID):
    if ID=="":
        return 'Error - No ID'
    else:
        artifacts=""
        artifact_list=colartifacts.find({"Sighting":ObjectId(ID)})
        #print(artifact_list)
        for artifact in artifact_list:
            #artifact=colartifacts.find_one({"_id":art_ID})
            art_ID=artifact.get("_id","")
            ref=artifact.get("References","")
            if ref!="":
                blob=ref.get("s3_image_name")
                print(art_ID,blob)
                try:
                    container_client.delete_blob(blob)
                except:
                    print("Error deleting Blob: ",blob)
                    continue
            colartifacts.delete_one({"_id":ObjectId(art_ID)})
        colsightings.delete_one({"_id":ObjectId(ID)})
        return 'OK'

def add_record(collection,data):
    try:
        id = collection.insert_one(data).inserted_id
    except:
        print("Error adding record")
        return "ERROR"
    else:
        return "OK:"+str(id)
    
