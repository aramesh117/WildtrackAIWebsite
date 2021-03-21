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

def del_record(collection,ID):
    if ID=="":
        return 'Error - No ID'
    else:
        try:
            collection.delete_one({"_id":ObjectId(ID)})
        except:
            return 'Error deleting record: '+str(ID)
        else:
            return 'OK'
    

def create_observation(data,files,source="wildtrack-website"):
    print(data)


    #feedback["Images"]=data.get("images","")
    #instance=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    update=data.get("date","")
    if update=="":
        instance=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        instance=update+"T00:00:00Z"
    #print(formdate,instance)
    #forminstance=formdate.strftime("%Y-%m-%dT%H:%M:%SZ")
    #print(forminstance)
    #print("Adding feedback",request.values,feedback)
    # Define MongoDB Sighting collection schema
    sighting_schema = {
        'RecorderInfo': {
            'Name': data.get("newname",""),
            'Email': data.get("newemail",""),
            'Organization': data.get("org","")},
        'TimeStamp': {
            'created_at': instance,
            'uploaded_at': instance},
        'Location': {
            'LocationName': '',
            'GPS': {}},
        'UserLabels': {
            'Species': data.get("species",""),
            'AnimalName': data.get("animalname",""),
            'AnimalID': data.get("animalid",""),
            'Sex': data.get("sex","")},
        'References': {
            'Source': source},
        'Comments': {
            'UserComments': data.get("notes","")}
        }



    # Remove null schema values and post record to MongoDB
    cleanSightingSchema = cleanNullTerms(sighting_schema)
    sighting_id = db.Sightings.insert_one(cleanSightingSchema).inserted_id
    
    uploaded_files=request.files.getlist('images')
    print(len(uploaded_files))
    for image in uploaded_files:
        #uploaded_file.save(uploaded_file.filename)
        print(image.filename)
# Establish IBM COS client and write directly to S3
        id = uuid.uuid1().hex
        image_name = "WILDTRACKDIRECT/"+id+".jpg"
        #cos.meta.client.upload_fileobj(image,
        #                            Bucket = BLOB_BUCKET,
        #                            Key = image_name)
        #data=open(image, "rb")
        img = BytesIO(image.read())        
        data = Image.open(img, 'r')        
        buf = BytesIO()        
        data.save(buf, 'png')   
        container_client.upload_blob(name=image_name, data=buf.getvalue())
        artifact_schema = {
        'ArtifactType': data.get("artifacttype","footprints"),
        'MediaType': data.get("mediatype",'photo'),
        'Sighting' : sighting_id,
        'TimeStamp': {
            'created_at': '',
            'uploaded_at': ''},
        'References': {
            'Source': source,
            's3_image_name': image_name},
        'UserLabells': {
            'Foot':data.get ("foot",""),
            'FootprintID': data.get("footprintid","")}
        }

        cleanArtifactSchema = cleanNullTerms(artifact_schema)
        artifact_id = db.Artifacts.insert_one(cleanArtifactSchema)
        print("Artifact: ",artifact_id)





        #print(feedbackid)
    #except:
    #    print("Error adding feedback")
    #    status="Error"
    #else:
    status="OK "+str(sighting_id)
    return status
    