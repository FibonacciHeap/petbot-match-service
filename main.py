from flask import Flask, jsonify, request
import json
from math import sqrt, exp, cos, sin, atan2
from multiprocessing.dummy import Pool
import time
import requests
import json

app = Flask(__name__)
pool = Pool(processes=1)

#####################################################
# CONSTANTS
#####################################################

OWNER_REPORTED_DB_TABLE_NAME = 'OwnerReports'
SAMARITAN_REPORTED_DB_TABLE_NAME = 'SamaritanReports'
MAX_COLOR_DELTA = 764.8339663572415
NLU_MATCH_URL = "https://pd-messenger-bot.herokuapp.com/webhook?hub.verify_token=TOKEN&hub.mode=subscribe"

# Credits: http://stackoverflow.com/questions/4296249/
# how-do-i-convert-a-hex-triplet-to-an-rgb-tuple-and-back
_NUMERALS = '0123456789abcdefABCDEF'
_HEXDEC = {v: int(v, 16) for v in (x+y for x in _NUMERALS for y in _NUMERALS)}
LOWERCASE, UPPERCASE = 'x', 'X'

def rgb(triplet):
    triplet = triplet[1:]
    return _HEXDEC[triplet[0:2]], _HEXDEC[triplet[2:4]], _HEXDEC[triplet[4:6]]

def triplet(rgb, lettercase=LOWERCASE):
    return str('#' + format(rgb[0]<<16 | rgb[1]<<8 | rgb[2], '06'+lettercase))

#####################################################
# ROUTES
#####################################################

@app.route('/')
def index():
    match = {
              "facebookID": "1245562518853936",
              "imageURL": "https://s-media-cache-ak0.pinimg.com/736x/2e/b9/1a/2eb91a76325d9c406ab97e981990ad78.jpg",
              "petType": "monster",
              "confidence": "0.88",
              "caregiverName": "The Doggo Paradise",
              "caregiverAddress": "1555 Haste St, Berkeley, CA"
            }
    notify_match_to_user(match)
    return 'Hi, I am up :)'

@app.route('/match/check', methods=['POST'])
def check_match():
    # Get pet data
    pet_data = request.data
    if type(pet_data) == str:
        #return jsonify({"Error": "Could not read the request data."}), 400
        pet_data = json.loads(pet_data)

    pet = pet_data["pet"]
    other_pets = pet_data["otherPets"]

    # Asynchronously run check match routine
    # callback = lambda: log_data("Finished match at", time.time())
    # pool.apply_async(check_match_routine, args=[pet, other_pets], callback=callback)
    match = check_match_routine(pet, other_pets)

    # Acknowledge that match is being checked
    return jsonify(match)

#####################################################
# HELPERS
#####################################################

def check_match_routine(pet, closest_pets):
    """
    Check if there is a match with the pet and notify
    NLU service if there is.
    """
    # 1. Run matching algorithm between the current
    #    animal and the closest ones
    closest_pets = assign_match_scores(pet, closest_pets)

    # 2. Send top animal information to NLU svc
    match = create_match_request(pet, closest_pets)
    if not match:
        return jsonify({})

    print("Match is", match)
    notify_match_to_user(match)
    return match

def notify_match_to_user(match):
    """
    Notify the User service about a new match.
    """

    body = {
        "object": "special",
        "data": match
    }

    headers = { "Content-Type" : "application/json" }

    print ("Sending match", match)
    r = requests.post(NLU_MATCH_URL, data=json.dumps(body), headers=headers)
    print ("    Succeess?", r.status_code, r.text)

def create_match_request(pet, possible_pets):
    """
    Return a JSON with relevant match information:
          {
              "facebookID": <text>,
              "imageURL": <text>,
              "petType": <text>,
              "confidence": <float>,
              "caregiverName": <text>,
              "caregiverAddress": <text>
          }
    """
    print("Candidates", possible_pets)
    best_match = max(possible_pets, key=lambda pet: pet["confidence"])
    if best_match["confidence"] < 0.25:
        return None
    best_match = pet if pet["reportType"] == "owner" else best_match
    match_dict = {
        "facebookID": best_match["userID"],
        "imageURL": best_match["url"],
        "petType": best_match["petType"],
        "confidence": best_match["confidence"],
        "caregiverName": "Happy Paws & Claws",
        "caregiverAddress": "1555 Haste St, Berkeley, CA"
    }
    return match_dict

def assign_color_difference(color, possible_pets):
    def calculate_color_difference(color1, color2):
        """
        Range is [0, 764.8339663572415].
        """
        rgb1, rgb2 = rgb(color1), rgb(color2)
        r = (rgb1[0] + rgb2[0])/2
        delta_r = rgb1[0] - rgb2[0]
        delta_g = rgb1[1] - rgb2[1]
        delta_b = rgb1[2] - rgb2[2]
        delta_c = sqrt((2+r/256)*delta_r**2 + 4*delta_g**2 \
                  + (2+(255-r)/256)*delta_b**2)
        return delta_c
    for pet in possible_pets:
        pet["colorDelta"] = calculate_color_difference(color, pet["color"])
    return possible_pets

def assign_distances(lat, lon, possible_pets):
    for p in possible_pets:
        p["distance"] = mt_to_miles(lat, lon, p["reportLat"], p["reportLon"])
    return possible_pets

def assign_match_scores(pet, possible_pets):
    def calculate_match_score(p):
        w1, w2 = 0.75, 0.25
        sigmoid_g1 = lambda x: (1 - (1/(1+100*exp(-0.5*x))))
        linear_g2 = lambda x: 1 - (x/MAX_COLOR_DELTA)
        probability_function = lambda x, y: w1*sigmoid_g1(x) + w2*linear_g2(y)
        f1, f2 = p["distance"], p["colorDelta"]
        return probability_function(f1, f2)
    possible_pets = assign_distances(pet["reportLat"], pet["reportLon"], possible_pets)
    possible_pets = assign_color_difference(pet["color"], possible_pets)
    for p in possible_pets:
        p["confidence"] = calculate_match_score(p)
    return possible_pets

def mt_to_miles(lat1, lon1, lat2, lon2):
    return calculate_distance_in_mt(lat1, lon1, lat2, lon2)/1609.34

def calculate_distance_in_mt(lat1, lon1, lat2, lon2):
  R = 6371e3
  a1 = lat1 * (3.141592/180)
  a2 = lat2 * (3.141592/180)
  o = (lat2-lat1) * (3.141592/180)
  l = (lon2-lon1) * (3.141592/180)

  x = sin(o/2) * sin(o/2) + cos(a1) * cos(a2) * sin(l/2) * sin(l/2)
  c = 2 * atan2(sqrt(x), sqrt(1-x))
  d = R * c

  FEET_KM_CONSTANT = 3.280839895
  return d * FEET_KM_CONSTANT


def log_data(data):
    print("Log:", data)

#####################################################
# DATABASE
#####################################################


if __name__ == "__main__":
    app.run()

# NOT USING BREED ANYMORE
# def assign_breed_match(breed, possible_pets):
#     def calculate_breed_match(breed1, breed2):
#         """ TO IMPLEMENT """
#         pass
#     for pet in possible_pets:
#         pet["breedScore"] = calculate_breed_match(breed, pet["breed"])
#     return possible_pets

# NOT DOING QUERIES ANYMORE
# def get_table_to_query(pet_type):
#     if pet_type == "samaritan":
#         return OWNER_REPORTED_DB_TABLE_NAME
#     elif pet_type == "owner":
#         return SAMARITAN_REPORTED_DB_TABLE_NAME

# def get_closest_pets(pet, max_dist_in_miles = 50):
#     """
#     Runs a SQL query in Google App Engine to get
#     closest records.
#
#     Range of pet["distance"] is [0, max_dist_in_miles].
#     """
#     pass
