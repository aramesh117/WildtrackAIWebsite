# Revisions
# ************
# 12/2020 - JTD - Update to point to WildTrack MongoDB instance and Azure Blob Store



from flask import Flask,render_template,jsonify,request
from flask_basicauth import BasicAuth
import dns
import pymongo
import pprint
import ibm_boto3
from ibm_botocore.client import Config, ClientError
import io
import base64
import PIL
from PIL import Image,ImageDraw
from bson.objectid import ObjectId
from collections import defaultdict
import json
from datetime import datetime
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient, __version__
from DBUtils import *
import os

app = Flask(__name__)
app.config['BASIC_AUTH_USERNAME'] = 'wildtrackai'
app.config['BASIC_AUTH_PASSWORD'] = 'WildTrackAI'
basic_auth = BasicAuth(app)

wildtrack_env = os.environ.get('WILDTRACK_ENVIRONMENT',"")
print("env: ",wildtrack_env)
if wildtrack_env=="DEVELOPMENT":
    print("Connecting to Development")
    MONGO_DB='wildtrack-dev'
    AZURE_CONNECT_STRING = 'DefaultEndpointsProtocol=https;AccountName=wtimages01;AccountKey=k3BuXSlMiDyv+7ftWQqAPLKhu1OwIvd8W2/EjEjzVf/D/uSodDmCHp46KnGBFIaEBFpGHKdf5Jn9dxMkSWNqTQ==;EndpointSuffix=core.windows.net'
    AZURE_BLOB_CONTAINER = "wtimages01-dev01"
    AZURE_TEXT_CONTAINER = "wtimages01-dev02"
else:
    print("Connecting to Production")
    MONGO_DB='wildtrack-db01'
    AZURE_CONNECT_STRING = 'DefaultEndpointsProtocol=https;AccountName=wtimages01;AccountKey=k3BuXSlMiDyv+7ftWQqAPLKhu1OwIvd8W2/EjEjzVf/D/uSodDmCHp46KnGBFIaEBFpGHKdf5Jn9dxMkSWNqTQ==;EndpointSuffix=core.windows.net'
    AZURE_BLOB_CONTAINER = "wtimages01-prod01"
    AZURE_TEXT_CONTAINER = "wtimages01-prod02"

#JTD+5 12/2020
#COnstants for metadata and object locations
#BLOB_BUCKET="test-wildtrackai"
#TEXT_BUCKET="test-wildtrackai"
#MONGO_DB='wildtrack-db01'
#AZURE_CONNECT_STRING = 'DefaultEndpointsProtocol=https;AccountName=wtimages01;AccountKey=k3BuXSlMiDyv+7ftWQqAPLKhu1OwIvd8W2/EjEjzVf/D/uSodDmCHp46KnGBFIaEBFpGHKdf5Jn9dxMkSWNqTQ==;EndpointSuffix=core.windows.net'
#AZURE_BLOB_CONTAINER = "wtimages01-prod01"
#AZURE_TEXT_CONTAINER = "wtimages-1-prod02"

#Constants for Inference THRESHOLDS
DETECTION_THRESHOLD=70
SPECIES_THRESHOLD=20
INDIVIDUAL_THRESHOLD=10
USE_DETECTION_CLASSES=False
FIELD_FACTOR=1 #Multiply fielf confidences by this factor

#JTD+6 12/20 No longer needed
# Constants for IBM COS values
#COS_ENDPOINT = "https://s3.eu.cloud-object-storage.appdomain.cloud" # Current list avaiable at https://control.cloud-object-storage.cloud.ibm.com/v2/endpoints
#COS_API_KEY_ID = "F1lZCIsOoJtKsli1wJRa9L9r6Oz9K3jyuET26_KwGD1t" # eg "W00YixxxxxxxxxxMB-odB-2ySfTrFBIQQWanc--P3byk"
#COS_RESOURCE_CRN = "crn:v1:bluemix:public:cloud-object-storage:global:a/fd6505dcab2743a49886ba001521b883:b4a9771f-947a-4ed8-a47d-aa18426a43b2::" # eg "crn:v1:bluemix:public:cloud-object-storage:global:a/3bf0d9003xxxxxxxxxx1c3e97696b71c:d6f04d83-6c4f-4a62-a165-696756d63903::"
#COS_AUTH_ENDPOINT = "https://iam.cloud.ibm.com/identity/token"
# Create resource
#cos = ibm_boto3.resource("s3",
#    ibm_api_key_id=COS_API_KEY_ID,
#    ibm_service_instance_id=COS_RESOURCE_CRN,
#    ibm_auth_endpoint=COS_AUTH_ENDPOINT,
#    config=Config(signature_version="oauth"),
#    endpoint_url=COS_ENDPOINT
#)


#JTD+1 12/2020 Non longer needed
client = pymongo.MongoClient("mongodb+srv://mongoadmin:BmmfKb1UkIFbRFl5@cluster0.ybns4.azure.mongodb.net/admin?retryWrites=true&w=majority")
#client = pymongo.MongoClient("mongodb+srv://wildtrackdev:wildtrackai2020!@cluster0-abxwt.azure.mongodb.net/admin?retryWrites=true&w=majority")
db = client[MONGO_DB]
colsightings= db["Sightings"]
colartifacts= db["Artifacts"]
colfeedback=db["Feedback"]
colmodelsummaries=db["ModelSummaries"]
colspecies=db["Species"]

cursor=colspecies.find({"Modeled":True},{"SpeciesCommon":1,"_id":0},sort=[("SpeciesCommon",1)])
species_list=[]
for item in cursor:
    label=item.get("SpeciesCommon","")
    #print("label = ",label)
    if label!="" and "*" not in label:
        species_list.append(label)
Species_Master=sorted(species_list)
#print(Species_Master)
sightings={}
total_sightings_counter=0
artifacts={}
Images={}
artifact_count=0
trained_artifact_count=0
total_artifacts_counter=0
all_species_count=0
modeled_species_count=0
contributor_count=0
individual_count=0
species_accuracy=0
species_accuracy_count=0
species_quality=0
individual_accuracy=0
individual_accuracy_count=0
individual_quality=0
sex_accuracy=0
sex_accuracy_count=0
last_model_refresh=""
current_sightings_search=""
Alldocs=[]
species_image_counts = {}
#Species_Master=sorted(["Tiger: Amur","Tiger: Bengal","Cheetah: South East African","Leopard: African","Puma","Jaguar","Lion: African","Elephant: African",
#"Rhino: Black","Rhino: White","Tapir: Lowland","Bongo: Eastern Mountain","Otter: Eurasian","Panda: Giant"])
#Species_Master=sorted(["Amur Tiger","Bengal Tiger","Cheetah","Leopard","Puma","Jaguar","African lion","African elephant",
#"Black Rhino","White Rhino","Lowland Tapir","Bongo","Otter"])

def ClearCache():
    global sightings,artifacts,Images,current_sightings_search,Alldocs

    sightings={}
    artifacts={}
    Images={}
    current_sightings_search=""
    Alldocs=[]
    individual_count =0
    artifact_count = 0
    trained_artifact_count=0
    contributor_count=0
    all_species_count=0
    modeled_species_count=0
    species_accuracy=0
    individual_accuracy=0
    last_model_refresh=""




def get_item(bucket_name, item_name):
    #print("Retrieving item from bucket: {0}, key: {1}".format(bucket_name, item_name))
    try:
        file = cos.Object(bucket_name, item_name).get()
        image_stream=file["Body"].read()
        #print("File Contents: {0}".format(image_stream))
    except ClientError as be:
        print("CLIENT ERROR: {0}\n".format(be))
    except Exception as e:
        print("Unable to retrieve file contents: {0}".format(e))
    return image_stream

#JTD+8 12/2020 Get Azure Blob
#Retrieve Azure Blob object
def get_blob(item_name):
    #print("Retrieving item from bucket: {0}, key: {1}".format(bucket_name, item_name))
    try:
        blob = BlobClient.from_connection_string(conn_str=AZURE_CONNECT_STRING, container_name=AZURE_BLOB_CONTAINER, blob_name=item_name)
        blob_data = blob.download_blob()
        image_stream=blob_data.readall()
        #print("File Contents: {0}".format(image_stream))
    except ClientError as be:
        print("CLIENT ERROR: {0}\n".format(be))
    except Exception as e:
        print("Unable to retrieve file contents: {0}".format(e))
    return image_stream





def Get_Inference(value,confidence,threshold):
    if confidence=="nan":
        confidence=0
    if float(confidence)<float(threshold):
        result="Unknown"
    else:
        result=value+" ("+confidence+"%)"
    return result


def skiplimit(dbcoll,query_string={},project_string={},page_size=10, offset=0,sort=None,order=""):
    if order=="desc":
        order=-1
    else:
        order=1
    if sort:
        sort_str=[(sort,order)]
        #print("Sort String: ",sort_str)
        cursor=dbcoll.find(query_string,project_string).skip(offset).limit(page_size).sort(sort_str)
    else:
        cursor=dbcoll.find(query_string,project_string).skip(offset).limit(page_size)

    

    # Return documents
    result=[x for x in cursor]
    #print("results: ",len(result))
    return result

#Returns Submitted Feedback
@app.route('/get_feedback')
def get_feedback():
    cursor=db.Feedback.find({},{"_id":0})
    feedback=[doc for doc in cursor]
    #print(feedback)
    return jsonify(feedback)


#Gets Individuals given species
@app.route('/get_individuals')
def get_individuals():
    #cursor=db.Feedback.find({},{"_id":0})
    data=request.values
    #print(data)
    spec=data.get('Species')
    specmaster=colspecies.find_one({"SpeciesCommon":spec},{"Individuals":1})
    names=specmaster.get("Individuals",[])
    result=[item["AnimalName"] for item in names]
    #print(result)
    #result=[{"Name":"Jonathan"},{"Name":"Pantera"}]
    #print(feedback)
    return jsonify(result)


#Gets All Species and individuals for nodeled species
@app.route('/get_masterlists')
def get_masterlists():
    specieslist=[]
    ind_db=defaultdict(list)
    cursor=colspecies.find()
    for item in cursor:
        species=item.get("SpeciesCommon","")
        if species=="":
            continue
        specieslist.append(species)
        animals=item.get("Individuals",[])
        ind_db[species]=[animal["AnimalName"] for animal in animals]
        ind_db[species].append('UNKNOWN')
    specieslist.append('UNKNOWN')
    result={"Species":specieslist,"Individuals":ind_db}
    #print(result)

    return jsonify(result)

@app.route('/feedback_page')
@basic_auth.required
def feedback_page():
    return render_template("feedback.html",sitetype="user")


@app.route('/feedback_admin_page')
@basic_auth.required
def feedback_admin_page():
    return render_template("feedback-admin.html",sitetype="admin")

@app.route('/get_feedback_admin')
def get_feedback_admin():
    cursor=db.Feedback.find()
    
    feedback = []

    for doc in cursor:
        doc['ID']=str(doc.pop('_id'))
        feedback.append(doc)
    

    Result={"total":len(feedback),"totalNotFiltered":len(feedback),"rows":feedback}

    return jsonify(Result)

@app.route('/update_feedback', methods=['POST'])    
def update_feedback():
    data=request.values
    ID=data.get('ID')
    field=data.get('Field')
    value=data.get('Value')

    db.Feedback.update_one({'_id': ObjectId(ID)}, {'$set': {field: value}})


#Returns Leaderboard for image contribution 
@app.route('/get_leaderboard')
def get_leaderboard():
    pipeline = [{'$lookup': {
            'from': 'Artifacts', 
            'localField': '_id', 
            'foreignField': 'Sighting', 
            'as': 'Artifacts'}},
             {'$unwind': {
            'path': '$Artifacts', 
            'includeArrayIndex': 'ArtifactIndex', 
            'preserveNullAndEmptyArrays': True}},
             {'$project': {
            'RecorderInfo.Name': 1}},
             {'$group': {
            '_id': '$RecorderInfo.Name', 
            'Count': {'$sum': 1}}},
             {'$sort': {'Count': -1}}
            ]
    leaderboard = list(db.Sightings.aggregate(pipeline))
    #print("Leaderboard",leaderboard)
    numLeaders = 5
    result=leaderboard[0:numLeaders]
    #print("Top 5",result)
    return jsonify(result)


#Returns Leaderboard for image contribution 
@app.route('/get_leaderboard_monthly')
def get_leaderboard_monthly():

    # Parse year and month from current date for filtering
    today = datetime.today()
    year = today.year
    month = today.month

    pipeline = [{
    # Parse year and month from uploaded_at date
    '$project': {
        'RecorderInfo.Name': 1,
        'year': {'$year': {'$toDate': '$TimeStamp.uploaded_at'}},
        'month': {'$month': {'$toDate': '$TimeStamp.uploaded_at'}}
        }},
        {
    # Filter results by current year and month
    '$match': {
        'year': year,
        'month': month
        }},
        {
    # Join sightings to artifacts collection
    '$lookup': {
        'from': 'Artifacts', 
        'localField': '_id', 
        'foreignField': 'Sighting', 
        'as': 'Artifacts'
        }}, 
        {
    # Flatten artifacts arrays
    '$unwind': {
        'path': '$Artifacts', 
        'includeArrayIndex': 'ArtifactIndex', 
        'preserveNullAndEmptyArrays': True
        }}, 
        {
    # Extract just recorder name
    '$project': {
        'RecorderInfo.Name': 1
        }}, 
        {
    # Group by recorder name and count
    '$group': {
        '_id': '$RecorderInfo.Name', 
        'Count': {
            '$sum': 1
        }}}, 
        {
    # Sort results in descending order
    '$sort': {'Count': -1
        }}]
    leaderboard = list(db.Sightings.aggregate(pipeline))
    #print("Leaderboard",leaderboard)
    numLeaders = 5
    result=leaderboard[0:numLeaders]
    #print("Top 5",result)
    return jsonify(result)

#Returns summary string for accuracy
def summarize(stats):
    #print(stats)
    correct=stats["Correct"]
    total=stats["Total"]
    if stats["Accuracy"]!="":
        accuracy=str(round(100*stats["Accuracy"],2))+"%"
    else:
        accuracy=stats["Accuracy"]
    result=accuracy+" <span class=\"text-muted\"><small>("+str(correct)+"/"+str(total)+")</small</span>"

    return result



#Returns Latest Model Performance Statistics
@app.route('/get_model_stats')
def get_model_stats(jsonified=True,task='Individual_Identification'):
    result=[]
    cursor=colmodelsummaries.find().sort([("TimeStamp",-1)])
    TASK=request.args.get('task')
    if TASK is None:
        TASK = task
    for summary in cursor:
        #print(summary)
        categories=Species_Master.copy()
        #print(categories)
        categories.append("All")
        for species in categories:
            line={}
            info=summary["Summary_Metrics"].get(TASK,"")
            try:
                for tag,data in info[species].items():
                    #print("data: ",data)
                    if tag=="Overall":
                        continue
                    if jsonified:
                        line[tag]=summarize(data)
                    else:
                        line[tag]=str(round(100*data["Accuracy"],2))
                line["header"]=species
            except:
                print("Error retrieving Model stats",tag,data)
            result.append(line)

        break

    #print(result)
    if jsonified:
        return jsonify(result)
    else:
        return result

def get_species_foot_count():
    global colartifacts, species_image_counts
    speciesCount = colartifacts.aggregate([
        {
            "$lookup": {
                "from": "Sightings",
                "localField": "Sighting",
                "foreignField": "_id",
                "as": "Sighting"
            }
        }, {
            "$group": {
                "_id": {
                    "species": "$Species_Inference.value",
                    "foot": "$UserLabels.Foot"
                },
                "count": {
                "$sum": 1
                }
            }
        }
    ])

    species_count = {}
    for record in speciesCount:
        foot = record["_id"].get("foot","")
        if foot:
            species = record["_id"].get("species","")
            if species not in species_count.keys():
                left_front = right_front = left_hind = right_hind = unknown = 0
                if foot.lower() in ["lh","left hind"]:
                    left_hind = record["count"]
                elif foot.lower() in ["rh","right hind"]:
                    right_hind = record["count"]
                elif foot.lower() in ["lf","left front"]:
                    left_front = record["count"]
                elif foot.lower() in ["rf","right front"]:
                    right_front = record["count"]
                elif foot.lower() in ["unknown"]:
                    unknown = record["count"]

                species_count[species] = {"Left Hind":left_hind,"Right Hind":right_hind,"Left Front":left_front,"Right Front":right_front,"Unknown":unknown}
            else:
                if foot.lower() in ["lh","left hind"]:
                    species_count[species]["Left Hind"] += record["count"]
                elif foot.lower() in ["rh","right hind"]:
                    species_count[species]["Right Hind"] += record["count"]
                elif foot.lower() in ["lf","left front"]:
                    species_count[species]["Left Front"] += record["count"]
                elif foot.lower() in ["rf","right front"]:
                    species_count[species]["Right Front"] += record["count"]
                elif foot.lower() in ["unknown"]:
                    species_count[species]["Unknown"] += record["count"]   

    if species_image_counts == {}:
        species_image_counts = get_species_image_count()

    for species in species_count.keys():
        total_feet = species_count[species]["Left Hind"] +  species_count[species]["Right Hind"] +  \
                        species_count[species]["Left Front"] + species_count[species]["Right Front"] + \
                            species_count[species]["Unknown"]
        #if total_feet < species_image_counts[species]:
        #    species_count[species]["Unknown"] += species_image_counts[species] - total_feet
        species_count[species]["species"] = species

    species_count_list = []
    for species in species_count.keys():
        species_count_list.append( species_count[species] )               
    #print(species_count_list)
    return species_count_list


def get_species_image_count():
    global colartifacts
    speciesCount = colartifacts.aggregate([
        {
            "$lookup": {
                "from": "Sightings",
                "localField": "Sighting",
                "foreignField": "_id",
                "as": "Sighting"
            }
        }, {
            "$group": {
                "_id": "$Species_Inference.value",
                "count": {
                "$sum": 1
                }
            }
        }
    ])
    species_count = {}
    for species in speciesCount:
        if species["_id"] != None:
            species_count.update({species["_id"]:species["count"]})
    return species_count


def get_individuals_by_species():
    global colsightings

    individuals_by_species = {}

    for sighting in colsightings.find():
        References = sighting.get("References","")
        if References:
            Source = References.get("Source","")

        ExpertLabels=sighting.get("ExpertLabels","")
        if ExpertLabels:
            Species=ExpertLabels.get("Species","")
            AnimalName=ExpertLabels.get("AnimalName","")
            Sex = ExpertLabels.get("Sex","")
        else:
            UserLabels=sighting.get("UserLabels","")
            if UserLabels:
                Species=UserLabels.get("Species","")
                if Species == "Other":
                    Species=UserLabels.get("OtherSpecies","")

                AnimalName=UserLabels.get("AnimalName","")
                if AnimalName == "":
                    AnimalName = str(sighting.get("_id"))

                Sex=UserLabels.get("Sex","")
                if Sex=="" or Sex.lower()=="unknown":
                    Sex="U"
                elif Sex.lower()=="female":
                    Sex="F"
                elif Sex.lower()=="male":
                    Sex="M"
        #print(Species,AnimalName,Sex,Source)
        if Species and AnimalName and Sex and Source == "WildTrackAI-Train":
            animalID = (AnimalName,Sex)
            if Species in individuals_by_species:
                individuals_by_species[Species] = {animalID}.union(individuals_by_species[Species])
            else:
                individuals_by_species[Species] = {animalID}
    print(individuals_by_species)
    return individuals_by_species  


#Returns Artifact Statistics rolled up by species for landing page
@app.route('/get_species_stats')
def get_species_stats(jsonified=True):
    global total_artifacts_counter, colartifacts, colsightings, species_image_counts
    species_name_dict = {}
    species_count_list = []

    species_name_dict = get_individuals_by_species()
    if species_image_counts == {}:
        species_image_counts = get_species_image_count()
    #print("SPecies DIctionary: ",species_name_dict)
    for species in Species_Master:
        #species_name_dict.keys():
        individuals = males = females = unknowns = 0
        try:
            for individual in species_name_dict[species]:
                individuals += 1
                females  += (individual[1] == 'F')
                males    += (individual[1] == 'M')
                unknowns += (individual[1] == 'U')
            image_count = species_image_counts[species] if species in species_image_counts.keys() else 0
            species_count_list.append( {"species":species, "individual":individuals, "images":image_count, "females":females, "males":males, "unknown":unknowns} )
        except:
            print("Error getting species stats for ",species)
            continue
    #individual_count = 0
    #for species in species_count_list:
    #    individual_count += species[1]
    #
    #if total_artifacts_counter == 0:
    #    total_artifacts_counter = colartifacts.count_documents({"References.s3_image_name":{"$exists":1}})
    #    artifact_count = total_artifacts_counter
    #else:
    #    artifact_count = total_artifacts_counter
    if jsonified:
        return jsonify(species_count_list)
    else:
        #print(species_count_list)
        return species_count_list


def getcount(doc,mltype,label):
    info=doc.get(mltype,"")
    if info!="":
        if label=="Rating":
            count=float(info.get(label,0))
        else:
            count=int(info.get(label,0))
    else:
        count=0
    return count

def index(sitetype="user"):
    global artifact_count, trained_artifact_count,colartifacts, colsightings, last_model_refresh,colmodelsummaries,contributor_count
    global all_species_count,modeled_species_count,individual_count,species_accuracy,species_accuracy_count,individual_accuracy, individual_accuracy_count
    global sex_accuracy,sex_accuracy_count,species_quality,individual_quality



    expertlist=colsightings.distinct("ExpertLabels.AnimalName")
    individual_count=len(expertlist)

 
    artifact_count = colartifacts.count_documents({"References.s3_image_name":{"$exists":1}})

    

    trained_artifact_count=colartifacts.count_documents({"References.s3_image_name":{"$exists":1},"MachineLearning.MLType":"Train"})

 

    contributor_count=len(colsightings.distinct("RecorderInfo.Name"))



    all_species_count=len(colsightings.distinct("UserLabels.Species"))



    modeled_species_count=colspecies.find({"Modeled":True}).count()


    cursor=colmodelsummaries.find().sort([("TimeStamp",-1)])

    for summary in cursor:
        speciesinfo=summary["Summary_Metrics"].get("Species_Classification","")
        #print(speciesinfo)
        if speciesinfo!="":
            correct=getcount(speciesinfo["All"],"Field","Correct")+getcount(speciesinfo["All"],"Test","Correct")
            total=getcount(speciesinfo["All"],"Field","Total")+getcount(speciesinfo["All"],"Test","Total")
            rating=getcount(speciesinfo["All"],"Field","Rating")+getcount(speciesinfo["All"],"Test","Rating")
            #print("Spec Numbers:",correct,total)
            if total>0:
                acc=correct/total
                qual=float(rating)/2.0
            else:
                acc=0
                qual=0


            species_accuracy=round(float(acc)*100)
            species_accuracy_count=total
            species_quality=round(float(qual),2)
        individualinfo=summary["Summary_Metrics"].get("Individual_Identification","")
        #print(individualinfo)
        if individualinfo!="":
            correct=getcount(individualinfo["All"],"Field","Correct")+getcount(individualinfo["All"],"Test","Correct")
            total=getcount(individualinfo["All"],"Field","Total")+getcount(individualinfo["All"],"Test","Total")
            rating=getcount(individualinfo["All"],"Field","Rating")+getcount(individualinfo["All"],"Test","Rating")
            #print("Ind Numbers:",correct,total)
            if total>0:
                acc=correct/total
                qual=float(rating)/2.0
            else:
                acc=0
                qual=0

            individual_accuracy=round(float(acc)*100)
            individual_accuracy_count=total
            individual_quality=round(float(qual),2)
        break



    
        
    model_summary=colmodelsummaries.find_one({},projection=["TimeStamp"],sort=[("TimeStamp",-1)])
    if model_summary is not None:
        last_model_refresh=model_summary.get("TimeStamp","")

    if sitetype=="user":
        template="home-user.html"
    else:
        template="home-admin.html"

    return render_template(template, num_images=artifact_count, num_training_images=trained_artifact_count,
            num_species_all=all_species_count,num_species=modeled_species_count,num_contributors=contributor_count,
            num_individuals=individual_count,species_accuracy=species_accuracy,species_accuracy_count=species_accuracy_count,species_quality=species_quality,
            individual_accuracy=individual_accuracy,individual_accuracy_count=individual_accuracy_count,individual_quality=individual_quality,
            last_model_refresh=last_model_refresh,species_data=get_species_stats(False),
            active='home', sitetype=sitetype)

@app.route('/')
def home():
    #print("user")
    result=index("user")
    return result



@app.route('/admin')
@basic_auth.required
def home_admin():
    #print("admin")
    result=index("admin")
    #print(result)
    return result




#Returns Quality Rating Scale for dropdown 
@app.route('/get_ratingscale')
def get_ratingscale():
    map={0:0,1:1,2: 2,3:3,4:4,5:5}
    return map

@app.route('/sightings_page')
#@basic_auth.required
def sightings_page():
    global last_model_refresh
    model_summary=colmodelsummaries.find_one({},projection=["TimeStamp"],sort=[("TimeStamp",-1)])
    if model_summary is not None:
        last_model_refresh=model_summary.get("TimeStamp","")
    return render_template("sightings.html", last_model_refresh=last_model_refresh,active="observations",sitetype="user")

@app.route('/sightings_admin_page')
@basic_auth.required
def sightings_admin_page():
    global last_model_refresh
    model_summary=colmodelsummaries.find_one({},projection=["TimeStamp"],sort=[("TimeStamp",-1)])
    if model_summary is not None:
        last_model_refresh=model_summary.get("TimeStamp","")
    return render_template("sightings-admin.html", last_model_refresh=last_model_refresh, active="observations",sitetype="admin")

def GetSightingDetail(sighting):
    record={}
    try:
        ID=sighting["_id"]
        record["ID"]=str(ID)
        RecorderInfo=sighting.get("RecorderInfo","")
        #print("RecorderInfo: ",RecorderInfo)
        if RecorderInfo != "":
            record["Name"]=RecorderInfo.get("Name","")
            record["Organization"]=RecorderInfo.get("Organization","")
            #**JTD Leaving in here from when we had data filing to wrong field name
            if record["Organization"]=="":
                record["Organization"]=RecorderInfo.get("Organization","")
        Comments=sighting.get("Comments","")
        if Comments !="":
            record["ExpertComments"]=Comments.get("ExpertComments","")
        else:
            record["ExpertComments"]=""
        TimeStamp=sighting.get("TimeStamp","")
        if TimeStamp != "":
            record["TimeStamp"]=TimeStamp.get("created_at","").split("T")[0]
        ExpertLabels=sighting.get("ExpertLabels","")
        if ExpertLabels != "":
            record["Species"]=ExpertLabels.get("Species","")
            record["Individual"]=ExpertLabels.get("AnimalName","")
            record["Sex"]=ExpertLabels.get("Sex","")
        UserLabels=sighting.get("UserLabels","")
        if UserLabels != "":
            if record.get("Species","")=="":
                record["Species"]=UserLabels.get("Species","")
                if record["Species"]=="Other":
                    record["Species"]=UserLabels.get("OtherSpecies","")
                #print("SPecies: ",blob["Species"])
            if record.get("Individual","")=="":
                record["Individual"]=UserLabels.get("AnimalName","")
            if record.get("Sex","")=="":
                record["Sex"]=UserLabels.get("Sex","")

        References=sighting.get("References","")
        if References != "":
            record["Source"]=References.get("Source","")

        Species_Inference=sighting.get("Species_Inference","")
        #print("Species Inference",Species_Inference)
        species=""
        individual=""
        if Species_Inference != "":
            species_value=Species_Inference.get("value","")
            species_confidence=Species_Inference.get("confidence","")
            Individual_Inference=sighting.get("Individual_Inference","")
            #print("Individual Inference",Individual_Inference)
            if Individual_Inference != "":
                ind_value=Individual_Inference.get("value","")
                ind_confidence=Individual_Inference.get("confidence","")
            if species_value!="":
                species=Get_Inference(species_value,species_confidence,SPECIES_THRESHOLD)
                if species=='Unknown':
                    individual='Unknown'
                elif ind_value!="":
                    individual=Get_Inference(ind_value,ind_confidence,INDIVIDUAL_THRESHOLD)
                record["Species_Inference"]=species
                record["Individual_Inference"]=individual
        #print("Getting Artifact Info")
        artifact_list=colartifacts.find({"Sighting":ID,"References.s3_image_name":{"$exists":1}})
        record["Artifacts"]=[]
        count=defaultdict(int)
        for artifact in artifact_list:
            record["Artifacts"].append(str(artifact["_id"]))
            type=artifact["ArtifactType"]
            #print(type)
            if type=="Footprint":
                type="footprints"
            count[type]+=1
        record["Images"]="Trails: "+str(count["trails"])+" \n Footprints: "+str(count["footprints"])
        #print(record["Images"])
    except:
        print("Issue getting metadata for sighting: ",sighting)
        print("Got so far..",record)
    return record

@app.route('/get_sightings')
def get_sightings():
    global sightings,total_sightings_counter
    global client,db,colsightings,colartifacts
    records=[]
    #print("Getting Params..")
    search_str=request.args.get('search')
    sort=request.args.get('sort',type=str,default="")
    order=request.args.get('order')
    offset=request.args.get("offset",type=int,default=1)
    limit=request.args.get("limit",type=int,default=10)
    #print("Params: ",search_str,sort,order,offset,limit)

    #Hardcode sort to reverse chronological for now
    sort="TimeStamp.created_at"
    order="desc"

    #print(mycol.database,mycol.full_name)
    if len(search_str)>0:
        query_string={"$text": { "$search": search_str } }
    else:
        query_string={}
    cursor=skiplimit(colsightings,query_string,None,limit,offset,sort,order)
    filtered_sightings_counter=colsightings.count_documents(query_string)
    if total_sightings_counter==0:
        total_sightings_counter=colsightings.count_documents({})
    #print(cursor)
    for doc in cursor:
        #try:
            ID=str(doc["_id"])
            #print(ID)
            #if ID in sightings.keys():
            #    sighting=sightings[ID]
            #else:
            sighting=GetSightingDetail(doc)
                #print(sighting)
            #    sightings[ID]=sighting
       # except:
            #print("Error getting sighting",ID)
            #continue
        #else:
            records.append(sighting)
        

    Result={"total":filtered_sightings_counter,"totalNotFiltered":total_sightings_counter,"rows":records}
    #print(Result)
    return jsonify(Result)

#Given current species and individual prediction, returns updated one if candidate predicton 
# has higher confidence scores
def UpdateBestPredictions(species_current,individual_current,species_new,individual_new):
    #print("Updating... ",(species_current,individual_current,species_new,individual_new))
    sconf_current=species_current.get("confidence",0)
    sconf_new=species_new.get("confidence",0)
    result=[species_current,individual_current]
    if float(sconf_new)>SPECIES_THRESHOLD and float(sconf_new)>float(sconf_current):
        
        result=[species_new,individual_new]
    #print("Best result: ",result)
    return result




def GetArtifactPredictions(artifact,Species_Master):
    AIUse=""
    MachineLearning=artifact.get("MachineLearning","")
    if MachineLearning != "":
        AIUse=MachineLearning.get("MLType","")       

    
    Species_Inference=artifact.get("Species_Inference",{})
    Individual_Inference=artifact.get("Individual_Inference",{})
    best_spec={"value":"","confidence":0}
    best_ind={"value":"","confidence":0}
    best_spec,best_ind=UpdateBestPredictions(best_spec,best_ind,Species_Inference,Individual_Inference)
    #print("First Best: ",best_spec,best_ind)
    
    if AIUse=="":
        num_detections=len(artifact.get("Footprint_Detection",""))
        #print("Detections: ",num_detections)
        if num_detections>0:
            individuals=""
            species=""
            detected_species_prediction=""
            for i in range(num_detections):
                #try:
                    #Species_Inference=artifact["Footprint_Detection"][i].get("Species_Inference","")
                    #DO not process if species inference is empty (implies not highest confidence print/ inference didn't run)
                    #if Species_Inference=="":
                    #    continue
                    #if USE_DETECTION_CLASSES:
                    #    detected_species_prediction=artifact["Footprint_Detection"][i].get("value","")


                    #    if detected_species_prediction!="":
                    #        #detected_species_confidence=artifact["Footprint_Detection"][i].get("confidence",0)
                    #        detected_species_confidence=min(100,round(float(artifact["Footprint_Detection"][i].get("confidence",0))*FIELD_FACTOR,2))
                    #        Detected_Individual_Inference=artifact["Footprint_Detection"][i].get("Detected_Individual_Inference","")
                    #        if Detected_Individual_Inference=="":
                    #            #print("Its null!")
                    #            Detected_Individual_Inference={"value":"","confidence":0}
                    #        best_spec,best_ind=UpdateBestPredictions(best_spec,best_ind,{"value":detected_species_prediction,"confidence":detected_species_confidence},
                    #        Detected_Individual_Inference)#

                    #        #print("Detected & Classified: ",best_spec,best_ind)
                    detection_confidence=float(artifact["Footprint_Detection"][i].get("confidence",0))
                    
                    Species_Inference=artifact["Footprint_Detection"][i].get("Species_Inference","")
                    if Species_Inference =="":
                                Species_Inference={"value":"","confidence":0}
                    if detection_confidence>DETECTION_THRESHOLD and Species_Inference!="":
                        #print(Species_Inference)
                        cropped_species_inference=Species_Inference.get("value","")
                        multiplier=FIELD_FACTOR
                        species_conf=min(100,round(float(Species_Inference.get("confidence",0))*multiplier,2))
                        Species_Inference={"value":cropped_species_inference,"confidence":species_conf}
                        if Species_Inference != "":
                            Individual_Inference=artifact["Footprint_Detection"][i].get("Individual_Inference","")
                            if Individual_Inference =="":
                                Individual_Inference={"value":"","confidence":0}
                            best_spec,best_ind=UpdateBestPredictions(best_spec,best_ind,Species_Inference,Individual_Inference)  
                            #print("Detected: ",best_spec,best_ind)
                #except:
                    #print("Issue retrieving detection info for atrifact: ")
                    #continue

    spec_prediction=best_spec.get("value","")
    spec_confidence=best_spec.get("confidence",0)
    if spec_confidence=="":
        spec_confidence=0
    ind_prediction=best_ind.get("value","")
    ind_confidence=best_ind.get("confidence",0)
    if ind_confidence=="":
        ind_confidence=0
    return(spec_prediction,spec_confidence,ind_prediction,ind_confidence)



def GetArtifactDetail(artifact):
    blob={}
    #print(artifact)
    try:
        blob["ID"]=str(artifact["_id"])
        blob["Sighting"]=str(artifact.get("Sighting",""))
        ExpertLabels=artifact.get("ExpertLabels","")
        if ExpertLabels != "":
            blob["Foot"]=ExpertLabels.get("Foot","")
            blob["Rating"]=ExpertLabels.get("Rating","")
        UserLabels=artifact.get("UserLabels","")
        if UserLabels != "":
            if blob.get("Foot","")=="":
                blob["Foot"]=UserLabels.get("Foot","")
        Comments=artifact.get("Comments","")
        if Comments != "":
            blob["UserComments"]=Comments.get("UserComments","")
            blob["ExpertComments"]=Comments.get("ExpertComments","")
        MachineLearning=artifact.get("MachineLearning","")
        if MachineLearning != "":
            blob["AI_Use"]=MachineLearning.get("MLType","")
            if MachineLearning.get("Reference_Image","")==True:
                blob["Reference"]="Y"
        References=artifact.get("References","")
        filename=""
        if References != "":
            filename=References.get("s3_image_name","")
            blob["Source"]=References.get("Source","")
    except:
        print("Issue getting metadata for artifact: ",artifact["_id"])
    else:
        #try:
        #JTD+2 12/2020 Switch to Azure Blob Store
        #image_stream=get_item(BLOB_BUCKET,filename)
        image_stream=get_blob(filename)
        num_detections=len(artifact.get("Footprint_Detection",""))
        #blob["annotated_image"]="data:image/jpeg;base64,"+((base64.b64encode(image_stream)).decode('UTF-8'))
        #print("In: ",num_detections)
        #if num_detections==0 and len(image_stream)>0:
        if len(image_stream)>0:
            blob["annotated_image"]="<img src=\"data:image/jpeg;base64,"+((base64.b64encode(image_stream)).decode('UTF-8')+
            "\" class=\"img-fluid img-thumbnail\" alt=\"Annotated images\" loading=\"lazy\" width=\"260\" height=\"260\">")
        #try:
            #best_spec={"value":"","confidence":0}
            #best_ind={"value":"","confidence":0}
            #Species_Inference=artifact.get("Species_Inference","")
            #if Species_Inference!="":
            #    Individual_Inference=artifact.get("Individual_Inference","")
            #    best_spec,best_ind=UpdateBestPredictions(best_spec,best_ind,Species_Inference,Individual_Inference)
                #print("First Best: ",best_spec,best_ind)

        #num_detections=len(artifact.get("Footprint_Detection",""))
        #print("Detections: ",num_detections)
        #if num_detections>0:
        #    individuals=""
        #    species=""
        #    img=Image.open(io.BytesIO(image_stream))

        #    draw = ImageDraw.Draw(img)

        #    for i in range(num_detections):
                
        #        coordinates=artifact["Footprint_Detection"][i]["coordinates"].split(',')
        #        confidence=float(artifact["Footprint_Detection"][i]["confidence"])
                
        #        if confidence>float(DETECTION_THRESHOLD):
        #            shape=[float(coordinates[0]),float(coordinates[1]),float(coordinates[2]),float(coordinates[3])]
        #            #print(coordinates)
        #            #print("Shape: ",shape)
        #            print(confidence,DETECTION_THRESHOLD)
        #            draw.rectangle(shape, fill =None, outline ="yellow",width=20) 
            
        #    byteIO = io.BytesIO()

        #    img.save(byteIO, format='JPEG',quality=60)
        #    byteArr = byteIO.getvalue()

            #blob["annotated_image"]="<img src=\"data:image/jpeg;base64,"+((base64.b64encode(byteArr)).decode('UTF-8')+
            #"\" class=\"img-fluid img-thumbnail\" alt=\"Annotated images\" loading=\"lazy\" width=\"260\" height=\"260\"")

        spec_prediction,spec_confidence,ind_prediction,ind_confidence=GetArtifactPredictions(artifact,Species_Master)
        #print("NEW: ",spec_prediction,spec_confidence,ind_prediction,ind_confidence)

        if float(spec_confidence)>SPECIES_THRESHOLD:
            blob["Species_Inference"]=[spec_prediction+" ("+str(spec_confidence)+"%)"]

            if float(ind_confidence)>INDIVIDUAL_THRESHOLD:
                blob["Individual_Inference"]=[ind_prediction+" ("+str(ind_confidence)+"%)"]

            else:
                blob["Individual_Inference"]="Unknown"
        else:
            blob["Species_Inference"]="Unknown"
            blob["Individual_Inference"]="Unknown"

            #except:
            #    print("Could not obtain all inference info")
        #except:
        #    print("Issue getting image and detection info")

    return blob


@app.route('/get_details/')
def get_details():
    global sightings
    global artifacts
    records=[]
    sighting={}
    sightingID=request.args.get('sightingID')
    #print(request.args)
    #print(sightingID)
    #print("Getting details for Sighting: ",sightingID)
   #if len(sightings)>0:
   #     sighting=sightings.get(sightingID,{})
   # if sighting=={}:
 
    sighting=GetSightingDetail(colsightings.find_one({"_id":ObjectId(sightingID)}))
    #    sightings[sightingID]=sighting
    #artifact_list=sighting.get("Artifacts","")
    #if artifact_list=="":
    artifact_list=colartifacts.find({"Sighting":ObjectId(sightingID),"References.s3_image_name":{"$exists":1}},{"_id":1})
    #    sighting["Artifacts"]=[str(item["_id"]) for item in artifact_list]
 

    for doc in artifact_list:
        ID=doc.get("_id","")
        blob={}
        #if ID in artifacts.keys():
            #print("Retrieving from cache: ",ID)
        #    blob=artifacts[ID]
        #else:
            #print("Retrieving from server: ",ID)
        #print(ID)
        artifact=colartifacts.find_one({"_id":ObjectId(ID)})
        blob=GetArtifactDetail(artifact)
        #    artifacts[ID]=blob
        #print(blob)
        records.append(blob)
        
    total=len(records)
    Result={"total":total,"totalNotFiltered":total,"rows":records}
    #print(Result)
    return jsonify(Result)

@app.route('/images_page')
#@basic_auth.required
def images_page():
    global last_model_refresh
    model_summary=colmodelsummaries.find_one({},projection=["TimeStamp"],sort=[("TimeStamp",-1)])
    if model_summary is not None:
        last_model_refresh=model_summary.get("TimeStamp","")
    return render_template("images.html", last_model_refresh=last_model_refresh, active='images',sitetype="user")

@app.route('/images_admin_page')
@basic_auth.required
def images_admin_page():
    global last_model_refresh
    model_summary=colmodelsummaries.find_one({},projection=["TimeStamp"],sort=[("TimeStamp",-1)])
    if model_summary is not None:
        last_model_refresh=model_summary.get("TimeStamp","")
    return render_template("images-admin.html", last_model_refresh=last_model_refresh, active='images',sitetype="admin")

@app.route('/help')
def help_page():
    return render_template("help-user.html",  active='help',sitetype="user")

@app.route('/help_admin')
def help_admin_page():
    return render_template("help-admin.html",   active='help',sitetype="admin")

@app.route('/model')
def model_page():
    global last_model_refresh

    if last_model_refresh=="":
        model_summary=colmodelsummaries.find_one({},projection=["TimeStamp"],sort=[("TimeStamp",-1)])
        if model_summary is not None:
            last_model_refresh=model_summary.get("TimeStamp","")


    species_model_stats=get_model_stats(jsonified=False,task='Species_Classification')
    individual_model_stats=get_model_stats(jsonified=False,task='Individual_Identification')

    return render_template("model-user.html",  active='model',sitetype="user",species_data=get_species_stats(False), \
        foot_data=get_species_foot_count(),last_model_refresh=last_model_refresh,species_model_stats=species_model_stats, \
            individual_model_stats=individual_model_stats)


@app.route('/model_admin')
def model_admin_page():
    global last_model_refresh

    if last_model_refresh=="":
        model_summary=colmodelsummaries.find_one({},projection=["TimeStamp"],sort=[("TimeStamp",-1)])
        if model_summary is not None:
            last_model_refresh=model_summary.get("TimeStamp","")


    species_model_stats=get_model_stats(jsonified=False,task='Species_Classification')
    individual_model_stats=get_model_stats(jsonified=False,task='Individual_Identification')

    return render_template("model-admin.html",  active='model',sitetype="admin",species_data=get_species_stats(False), \
        foot_data=get_species_foot_count(),last_model_refresh=last_model_refresh,species_model_stats=species_model_stats, \
            individual_model_stats=individual_model_stats)


@app.route('/about')
def about_page():
    return render_template("about-user.html",  active='about',sitetype="user")

@app.route('/about_admin')
def about_admin_page():
    return render_template("about-admin.html",  active='about',sitetype="admin")

@app.route('/get_artifacts')    
def get_artifacts():
    global sightings,current_sightings_search
    global artifacts,total_artifacts_counter
    global client,db,colsightings,colartifacts
    blobtrack={}
    blobs=[]
    Alldocs=[]
    docIndx={}
    #print("Getting Params..")
    search_str=request.args.get('search')
    sort=request.args.get('sort')
    order=request.args.get('order')
    offset=request.args.get("offset",type=int,default=1)
    limit=request.args.get("limit",type=int,default=10)
    #print("Params: ",search,sort,order,offset,limit)
    #current_sightings_search=""
    if len(search_str)>0:
        #if current_sightings_search!=search_str:
        #    current_sightings_search=search_str
        if "|" in search_str:
            #print(search_str)
            collection,match=search_str.split("|")
            if collection=="S":
                pipeline=[{'$match': eval(match)},
                {'$lookup': {'from': 'Artifacts','localField': '_id','foreignField':'Sighting','as':'Artifacts'}}, {
                '$unwind': {'path': '$Artifacts','includeArrayIndex': 'iArtifact','preserveNullAndEmptyArrays': True}
                }]
                temp=colsightings.aggregate(pipeline)
                for item in temp:
                    doc=item.get("Artifacts","")
                    if doc:
                        docId=str(doc.get("_id",""))
                        Alldocs.append(doc)
            else:
                query_string=eval(match)
                #print(query_string)
                #Hardcoding sort to reverse chronological for now
                sort=[("TimeStamp.created_at",-1)]
                #print(mycol.database,mycol.full_name)
                #cursor=colartifacts.find({"References.s3_image_name":{"$exists":1}})
                #cursor=skiplimit(colartifacts,query_string,None)
                cursor=colartifacts.find(query_string,None).sort(sort)
                for doc in cursor:
                    docId=str(doc.get("_id",""))
                    #print(docId)
                    Alldocs.append(doc)

                #print(Alldocs)

        elif '#' in search_str:
            key,val=search_str.split("#")
            if key=="NoRating":
                if len(val)>0:
                    if val=="Field":
                        query_string={"References.s3_image_name":{"$exists":1},"ExpertLabels.Rating":{"$exists":0},"MachineLearning.MLType":{"$exists":0}}
                    else:
                        query_string={"References.s3_image_name":{"$exists":1},"ExpertLabels.Rating":{"$exists":0},"MachineLearning.MLType":val}
                else:
                    query_string={"References.s3_image_name":{"$exists":1},"ExpertLabels.Rating":{"$exists":0}}
                cursor=colartifacts.find(query_string,None).sort([("TimeStamp.created_at",-1)])
                for doc in cursor:
                    #docId=str(doc.get("_id",""))
                    #print(docId)
                    Alldocs.append(doc)               

        
        else:
            pipeline=[{'$match': {'$text': {'$search': search_str} }},
            {'$lookup': {'from': 'Artifacts','localField': '_id','foreignField':'Sighting','as':'Artifacts'}}, {
            '$unwind': {'path': '$Artifacts','includeArrayIndex': 'iArtifact','preserveNullAndEmptyArrays': True}
            }]
            temp=colsightings.aggregate(pipeline)
            for item in temp:
                doc=item.get("Artifacts","")
                if doc:
                    docId=str(doc.get("_id",""))
                    Alldocs.append(doc)
                    docIndx[docId]=1
                    #print("from sightings: ",docId)
            query_string={"References.s3_image_name":{"$exists":1},"$text": { "$search": search_str } }
            #Hardcoding sort to reverse chronological for now
            sort=[("TimeStamp.created_at",-1)]
            #print(mycol.database,mycol.full_name)
            #cursor=colartifacts.find({"References.s3_image_name":{"$exists":1}})
            cursor=colartifacts.find(query_string,None).sort(sort)
            #cursor=skiplimit(colartifacts,query_string)
            for doc in cursor:
                docId=str(doc.get("_id",""))
                if docId not in docIndx.keys():
                    Alldocs.append(doc)
                    docIndx[docId]=1
                    #print("from artifacts: ",docId)
            #print(Alldocs)
        docs=[]
        filtered_artifacts_counter=len(Alldocs)
        upper=min(offset+limit,filtered_artifacts_counter)
        #print("Filtered Artifacts: ",filtered_artifacts_counter,offset,upper)
        for i in range(offset,upper):
            #print(Alldocs[i])
            docs.append(Alldocs[i])
        
    else:
        query_string={"References.s3_image_name":{"$exists":1}}
        #Hardcoding sort to reverse chronological for now
        sort="TimeStamp.created_at"
        order="desc"
        #print(mycol.database,mycol.full_name)
        #cursor=colartifacts.find({"References.s3_image_name":{"$exists":1}})
        cursor=skiplimit(colartifacts,query_string,None,limit,offset,sort,order)
        filtered_artifacts_counter=colartifacts.count_documents(query_string)
        docs=[item for item in cursor]

    #if total_artifacts_counter==0:
    total_artifacts_counter=colartifacts.count_documents({"References.s3_image_name":{"$exists":1}})
    #print(cursor)
    for doc in docs:
        #try:

        ID=str(doc["_id"])
        blobtrack[ID]=1
        #print(ID)
        #if ID in artifacts.keys():
        #    artifact=artifacts[ID]
        #else:
        artifact=GetArtifactDetail(doc)
        #print(sighting)
        #artifacts[ID]=artifact

        sighting_id=artifact["Sighting"] 
        if sighting_id=="":
            print("NO SIGHTING!!")
            continue
            
        blob=artifact.copy()
        #print(sighting_id)
        #if sighting_id in sightings.keys():
            #print("Cache!")
        #    sighting=sightings[sighting_id]
        #else:
            #print("Server!")
        sighting_doc=colsightings.find_one({"_id": ObjectId(sighting_id)})
        sighting=GetSightingDetail(sighting_doc)
        #   sightings[sighting_id]=sighting
        blob["Name"]=sighting.get("Name")
        blob["Organization"]=sighting.get("Organization","")
        blob["TimeStamp"]=sighting.get("TimeStamp","").split("T")[0]
        blob["Species"]=sighting.get("Species","")
        blob["Individual"]=sighting.get("Individual","")
        blob["Sex"]=sighting.get("Sex","")
        sightingcomments=sighting.get("ExpertComments","")
        if sightingcomments!="":
            blob["CombinedComments"]=sightingcomments+" "+blob.get("ExpertComments","")
            #print("Combining!",blob["CombinedComments"])
        else:
            blob["CombinedComments"]=blob.get("ExpertComments","")
            #print(blob)
        #except:
            #print("Error getting artifact metadata",ID)
            #continue
        #else:
        blobs.append(blob)
    Result={"total":filtered_artifacts_counter,"totalNotFiltered":total_artifacts_counter,"rows":blobs}
    #print("RETURNING... ",filtered_artifacts_counter,total_artifacts_counter)
    return jsonify(Result)



# Gets original and annotated (with bounding boxes) images for an artifact
def GetImageDetails(artifact):
    blob={}
    try:
        blob["ID"]=str(artifact["_id"])
        References=artifact.get("References","")
        filename=""
        if References != "":
            filename=References.get("s3_image_name","")
            #JTD+2 12/2020 Switch to Azure BLOB store
            #image_stream=get_item(BLOB_BUCKET,filename)
            image_stream=get_blob(filename)
            num_detections=len(artifact.get("Footprint_Detection",""))

            blob["image"]="<img src=\"data:image/jpeg;base64,"+((base64.b64encode(image_stream)).decode('UTF-8')+
                "\" class=\"img-fluid img-thumbnail\" alt=\"Annotated images\" loading=\"lazy\" ")
            
            if num_detections>0:
                img=Image.open(io.BytesIO(image_stream))

                draw = ImageDraw.Draw(img)

                for i in range(num_detections):
                    confidence=float(artifact["Footprint_Detection"][i]["confidence"])
                    if confidence>float(DETECTION_THRESHOLD):
                        coordinates=artifact["Footprint_Detection"][i]["coordinates"].split(',')
                        shape=[(float(coordinates[0]),float(coordinates[1])),(float(coordinates[2]),float(coordinates[3]))]
                        draw.rectangle(shape, fill =None, outline ="yellow",width=7) 
                
                byteIO = io.BytesIO()
                img.save(byteIO, format='JPEG',quality=60)
                byteArr = byteIO.getvalue()
                blob["annotated_image"]="<img src=\"data:image/jpeg;base64,"+((base64.b64encode(byteArr)).decode('UTF-8')+
                "\" class=\"img-fluid img-thumbnail\" alt=\"Annotated images\" loading=\"lazy\" ")
    except:
        print("Issue getting Detailed Images")

    return blob




#Call from popup images in the images tab

@app.route('/get_images/')

def get_images():
    global Images

    ID=request.args.get('artifactID')
 
    blob={}
    if ID in Images.keys():
        #print("Retrieving from cache: ",ID)
        blob=Images[ID]
    else:
        #print("Retrieving from server: ",ID)
        artifact=colartifacts.find_one({"_id":ObjectId(ID)})
        blob=GetImageDetails(artifact)
        Images[ID]=blob
        #print(blob)


    Result={"total":1,"totalNotFiltered":1,"rows":[blob]}
    #print(Result)
    return jsonify(Result)

@app.route('/update_artifact_details', methods=['POST'])    
def update_artifact_details():
    try:
        #data=request.get_json()
        update_type="Artifact"
        data=request.values
        #print("DATA",request.data)
        ID=data.get('ID')
        #if ID in artifacts.keys():
        #    sightingID=artifacts[ID]["Sighting"]
        #else:
        doc=colartifacts.find_one({'_id':ObjectId(ID)},{'_id':0,"Sighting":1})
        sightingID=str(doc["Sighting"])
        #print("SightingID: ",sightingID)
        field=data.get('Field')
        value=data.get('Value')
        print("Updating Artifact",ID,sightingID,field,value)
        if field=="Foot":
            dbfield="ExpertLabels.Foot"
        elif field=="Rating":
            dbfield="ExpertLabels.Rating"
        elif field=="ExpertComments":
            dbfield="Comments.ExpertComments"
        elif sightingID!="":
            if field=="Species":
                update_type="Sighting"
                dbfield="ExpertLabels.Species"
            elif field=="Individual":
                update_type="Sighting"
                dbfield="ExpertLabels.AnimalName"
            elif field=="Sex":
                update_type="Sighting"
                dbfield="ExpertLabels.Sex"
            elif field=="Name":
                update_type="Sighting"
                dbfield="RecorderInfo.Name"
            elif field=="Organization":
                update_type="Sighting"
                dbfield="RecorderInfo.Organization"

        if update_type=="Artifact":
            colartifacts.update_one({'_id': ObjectId(ID)}, {'$set': {dbfield: value}})
            if ID in artifacts.keys():
                artifacts[ID][field]=value
        elif update_type=="Sighting":
            colsightings.update_one({'_id': ObjectId(sightingID)}, {'$set': {dbfield: value}})
            if sightingID in sightings.keys():
                sightings[sightingID][field]=value
            if ID in artifacts.keys():
                artifacts[ID][field]=value
        #print(ID,comment)
        ClearCache()
    except:
        print("Error saving details")
        status="Error"
    else:
        status="OK"
        return json.dumps({'status':status})

@app.route('/update_sighting_details', methods=['POST'])    
def update_sighting_details():
    try:
        #data=request.get_json()
        dbfield=""
        data=request.values
        #print("DATA",request.data)
        ID=data.get('ID')
        field=data.get('Field')
        value=data.get('Value')
        print("Updating sighting",ID,field,value)
        if field=="Species":
            dbfield="ExpertLabels.Species"
        elif field=="Individual":
            dbfield="ExpertLabels.AnimalName"
        elif field=="Sex":
            dbfield="ExpertLabels.Sex"
        elif field=="Name":
            dbfield="RecorderInfo.Name"
        elif field=="Organization":
            dbfield="RecorderInfo.Organization"
        elif field=="ExpertComments":
            dbfield="Comments.ExpertComments"
        if len(dbfield)>0:
            colsightings.update_one({'_id': ObjectId(ID)}, {'$set': {dbfield: value}})
            if ID in sightings.keys():
                sightings[ID][field]=value
                #print(ID,field,value)
        ClearCache()
    except:
        print("Error saving data for ",field)
        status="Error"
    else:
        status="OK"
        return json.dumps({'status':status})


#Save data from Feedback form
# TO DO : Send email?

@app.route('/add_feedback', methods=['POST'])    
def add_feedback():
    try:
        feedback=defaultdict()
        data=request.values
        feedback["Name"]=data.get("name","")
        feedback["Email"]=data.get("email","")
        feedback["Comments"]=data.get("feedback","")
        feedback["Rating"]=data.get("rating","")
        feedback["TimeStamp"]=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        #print("Adding feedback",request.values,feedback)
        feedbackid = colfeedback.insert_one(feedback).inserted_id
        #print(feedbackid)
    except:
        print("Error adding feedback")
        status="Error"
    else:
        status="OK"

    return json.dumps({'status':status})

@app.route('/update_image_details', methods=['POST'])    
def update_image_details():
    try:
        details=defaultdict()
        data=request.values
        #print("Request",request.values)
        ID=data.get("ID","")
        details["ExpertLabels.Rating"]=data.get("rating","")
        details["Comments.ExpertComments"]=data.get("comments","")
        mltype=data.get("mltype","")
        if mltype not in ["Train","Test"]:
            mltype=""
        details["MachineLearning.MLType"]=mltype
        details["MachineLearning.Reference"]=data.get("reference","")

        #print("Details",details)

        #if ID in artifacts.keys():
        #    sightingID=artifacts[ID]["Sighting"]
        #else:
        doc=colartifacts.find_one({'_id':ObjectId(ID)},{'_id':0,"Sighting":1})
        sightingID=str(doc["Sighting"])

        colartifacts.update_one({'_id': ObjectId(ID)}, {'$set': details})

        ClearCache()
        #feedbackid = colfeedback.insert_one(feedback).inserted_id
        #print(feedbackid)
    except:
        print("Errorupdating image details")
        status="Error"
    else:
        status="OK"

    return json.dumps({'status':status})

### User Management Section ###
@app.route('/users_admin_page')
def users_admin_page():
    return render_template("users-admin.html",sitetype="admin")

@app.route('/get_users')
def get_users():

    search_str=request.args.get('search')
    # sort=request.args.get('sort',type=str,default="")
    # order=request.args.get('order')
    sort='Name'
    order='asc'
    offset=request.args.get("offset",type=int,default=1)
    limit=request.args.get("limit",type=int,default=10)
    #("Params: ",search_str,sort,order,offset,limit)

    if len(search_str)>0:
        query_string={"$text": { "$search": search_str } }
    else:
        query_string={}

    cursor=skiplimit(db["Users"],query_string,None,limit,offset,sort,order)
    filtered_counter=db.Users.count_documents(query_string)
    users = []

    for doc in cursor:
        doc['ID']=str(doc.pop('_id'))
        users.append(doc)

    Result={"total": filtered_counter, "rows":users}
 
    return jsonify(Result)

@app.route('/update_user_details', methods=['POST'])    
def update_user_details():
    data=request.values
    ID=data.get('ID')
    field=data.get('Field')
    value=data.get('Value')

    db.Users.update_one({'_id': ObjectId(ID)}, {'$set': {field: value}})

### Species Management Section ###
@app.route('/species_admin_page')
def species_admin_page():
    return render_template("species-admin.html",sitetype="admin")

@app.route('/get_species')
def get_species():

    search_str=request.args.get('search')
    #sort=request.args.get('sort',type=str,default="")
    #order=request.args.get('order')
    sort='SpeciesCommon'
    order='asc'
    offset=request.args.get("offset",type=int,default=1)
    limit=request.args.get("limit",type=int,default=10)
    #print("Params: ",search_str,sort,order,offset,limit)

    if len(search_str)>0:
        query_string={"$text": { "$search": search_str } }
    else:
        query_string={}

    cursor=skiplimit(db["Species"],query_string,None,limit,offset,sort,order)
    filtered_counter=db.Species.count_documents(query_string)
    species = []

    for doc in cursor:
        doc['ID']=str(doc.pop('_id'))
        species.append(doc)

    Result={"total": filtered_counter, "rows":species}
 
    return jsonify(Result)

@app.route('/update_species_details', methods=['POST'])    
def update_species_details():
    data=request.values
    ID=data.get('ID')
    field=data.get('Field')
    value=data.get('Value')

    db.Species.update_one({'_id': ObjectId(ID)}, {'$set': {field: value}})

@app.route('/add_species',methods=['POST'])
def add_species():
    try:
        data=defaultdict()
        rqst=request.values
        #print("IN: ",rqst)
        data["SpeciesCommon"]=rqst.get("SpeciesCommon","")
        data["Genus"]=rqst.get("Genus","")
        data["SpeciesLatin"]=rqst.get("SpeciesLatin","")
        data["SubSpecies"]=rqst.get("SubSpecies","")
        #data["TimeStamp"]=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        result=add_record(db["Species"],data)
        #print(result)
    except:
        print("Error adding species information")
        status="Error"
    else:
        if result=="ERROR":
            status="Error"
        else:
            status="OK"
    
    return json.dumps({'status':status})
        

@app.route('/delete_species',methods=['POST'])
def delete_species():
    data=request.values
    ID=data.get('ID')
    status=del_record(db['Species'],ID)
    #print(status)
    return json.dumps({'status':status})


@app.route('/add_user',methods=['POST'])
def add_user():
    try:
        data=defaultdict()
        rqst=request.values
        #print("IN: ",rqst)
        data["Name"]=rqst.get("Name","")
        data["Organization"]=rqst.get("Organization","")
        data["Email"]=rqst.get("Email","")
        data["Description"]=rqst.get("Description","")
        #data["TimeStamp"]=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        result=add_record(db["Users"],data)
        #print(result)

    except:
        print("Error adding user information")
        status="Error"
    else:
        if result=="ERROR":
            status="Error"
        else:
            status="OK"

    return json.dumps({'status':status})

@app.route('/delete_user',methods=['POST'])
def delete_user():
    data=request.values
    ID=data.get('ID')
    status=del_record(db['Users'],ID)
    #print(status)
    return json.dumps({'status':status})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')


@app.route('/add_observation', methods=['POST'])   

def add_observation():
    #try:
    data=request.values
    files=request.files.getlist('images')
    result=Create_Observation(data,files)
    print(data)
    return json.dumps({'status':resullt})


   