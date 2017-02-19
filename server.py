from flask import Flask, jsonify
import json
from math import sqrt, exp
import threading

app = Flask(__name__)

#####################################################
# CONSTANTS
#####################################################

OWNER_REPORTED_DB_TABLE_NAME = 'owner'
SAMARITAN_REPORTED_DB_TABLE_NAME = 'samaritan'
MAX_COLOR_DELTA = 764.8339663572415

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
    return "Hi, I'm working :)"

@app.route('/match/check', methods=['POST'])
def check_match():
    # Get pet data
    data = request.data
    if type(data) == str:
        pet = json.loads(data)
    else:
        return jsonify({ "Error": "Could not read the request data."}), 400

    # Asynchronously run check match routine
    thr = threading.Thread(target=check_match_routine, args=(pet), kwargs={})
    thr.start()

    # Acknowledge that match is being checked
    return jsonify({}), 200

#####################################################
# HELPERS
#####################################################

def check_match_routine(pet):
    """
    Check if there is a match with the pet and notify
    NLU service if there is.
    """
    # 0. Decide which table to query (SR or OR)
    table_to_query = get_table_to_query(pet["type"])

    # 1. Get closest records within 100 miles radius
    #    that match in type, haven't been matched,
    #    and haven't been rejected
    closest_pets = get_closest_pets(pet)
    if (len(closest_pets) == 0):
        print("No matches for pet", pet["reportId"])
        return

    # 2. Run matching algorithm between the current
    #    animal and the closest ones
    assign_match_scores(pet, closest_pets)

    # 3. Send top animal information to NLU svc
    match = create_match_request(possible_pets)
    notify_match_to_nlu(match)

def notify_match_to_nlu(match):
    """
    Notify the NLU service about a new match.
    """
    pass

def create_match_request(possible_pets):
    """
    Return a JSON with relevant match information:
          {
              "imageURL": <text>,
              "petType": <text>,
              "confidence": <float>
          }
    """
    best_match = max(possible_pets, key=lambda pet: pet["confidence"])
    if best_match["confidence"] < 0.3:
        return None
    match_dict = {
        "imageURL": best_match["url"],
        "petType": best_match["type"],
        "confidence": best_match["confidence"]
    }
    return jsonify(match_dict)

def get_table_to_query(pet_type):
    if pet_type == "samaritan":
        return OWNER_REPORTED_DB_TABLE_NAME
    elif pet_type == "owner":
        return SAMARITAN_REPORTED_DB_TABLE_NAME

def get_closest_pets(pet, max_dist_in_miles = 50):
    """
    Runs a SQL query in Google App Engine to get
    closest records.

    Range of pet["distance"] is [0, max_dist_in_miles].
    """
    pass

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

def assign_match_scores(pet, possible_pets):
    def calculate_match_score(p):
        w1, w2 = 0.75, 0.25
        sigmoid_g1 = lambda x: (1 - (1/(1+100*exp(-0.5*x))))
        linear_g2 = lambda x: 1 - (x/MAX_COLOR_DELTA)
        probability_function = lambda x, y: w1*sigmoid_g1(x) + w2*linear_g2(y)
        f1, f2 = p["distance"], p["colorDelta"]
        return probability_function(f1, f2)
    assign_color_difference(pet["color"], closest_pets)
    for p in possible_pets:
        pet["confidence"] = calculate_match_score(p)
    return possible_pets


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
