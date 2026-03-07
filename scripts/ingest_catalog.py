"""
Catalog ingestion script — 500 products across 10 categories.
Ingests via the running API server (works with in-memory Qdrant).

Usage:
    # Make sure the server is running first
    python scripts/ingest_catalog.py
"""

import sys
import json
import urllib.request

BASE_URL = "http://localhost:8000"
TENANT_ID = "retailer_abc"

# --- Product Templates ---

CATALOG = {
    "running shoes": {
        "brands": {
            "Nike": [
                ("Air Zoom Pegasus", 2499, ["cushioned", "everyday running", "breathable"]),
                ("Air Zoom Wide Runner", 1899, ["wide fit", "cushioned", "lightweight"]),
                ("ZoomX Vaporfly", 4999, ["carbon plate", "race day", "lightweight"]),
                ("React Infinity", 3199, ["injury prevention", "cushioned", "stable"]),
                ("Free Run", 1999, ["flexible", "barefoot feel", "lightweight"]),
                ("Winflo", 1599, ["budget friendly", "cushioned", "beginner"]),
                ("Air Max Pulse", 2899, ["air cushioning", "retro", "comfortable"]),
                ("Pegasus Trail", 2799, ["trail running", "grippy", "waterproof"]),
                ("Zoom Fly", 3499, ["carbon plate", "tempo run", "fast"]),
                ("Revolution", 1299, ["budget friendly", "lightweight", "daily trainer"]),
            ],
            "Adidas": [
                ("Ultraboost 23", 3299, ["boost cushioning", "responsive", "premium"]),
                ("Runfalcon 3", 1299, ["budget friendly", "lightweight", "beginner"]),
                ("Adizero Adios Pro", 4499, ["carbon plate", "race day", "elite"]),
                ("Supernova Rise", 2299, ["dreamstrike", "cushioned", "daily trainer"]),
                ("Duramo Speed", 1499, ["budget friendly", "lightweight", "versatile"]),
                ("Solarglide", 2699, ["stable", "cushioned", "long distance"]),
                ("Adizero Boston", 3099, ["tempo run", "lightweight", "responsive"]),
                ("Questar", 1199, ["budget friendly", "comfortable", "beginner"]),
                ("Adistar", 2899, ["max cushion", "long distance", "premium"]),
                ("Galaxy", 999, ["budget friendly", "entry level", "daily wear"]),
            ],
            "Puma": [
                ("Velocity Nitro 2", 1999, ["nitro foam", "responsive", "fast"]),
                ("Deviate Nitro Elite", 3999, ["carbon plate", "race day", "elite"]),
                ("Magnify Nitro", 2499, ["max cushion", "long distance", "comfortable"]),
                ("Electrify Nitro", 1799, ["lightweight", "responsive", "daily trainer"]),
                ("ForeverRun Nitro", 2999, ["cushioned", "stable", "premium"]),
            ],
            "New Balance": [
                ("Fresh Foam 1080", 3499, ["max cushion", "premium", "comfortable"]),
                ("FuelCell Rebel", 2999, ["lightweight", "fast", "responsive"]),
                ("Fresh Foam 880", 2499, ["cushioned", "daily trainer", "versatile"]),
                ("FuelCell SuperComp Elite", 4999, ["carbon plate", "race day", "elite"]),
                ("Fresh Foam Arishi", 1499, ["budget friendly", "comfortable", "beginner"]),
            ],
            "Asics": [
                ("Gel-Nimbus 25", 3299, ["gel cushioning", "premium", "long distance"]),
                ("Gel-Kayano 30", 3499, ["stability", "overpronation", "premium"]),
                ("Gel-Cumulus 25", 2499, ["cushioned", "daily trainer", "versatile"]),
                ("Novablast 4", 2899, ["bouncy", "lightweight", "fast"]),
                ("GT-2000 12", 2699, ["stability", "cushioned", "daily trainer"]),
            ],
        },
        "sizes": ["6", "7", "8", "9", "10", "11", "12"],
        "colors": ["black", "white", "blue", "red", "grey", "green", "orange", "pink"],
    },
    "trekking shoes": {
        "brands": {
            "Woodland": [
                ("Adventure Trek", 1499, ["waterproof", "rugged", "ankle support"]),
                ("Everest Pro", 2199, ["waterproof", "insulated", "high altitude"]),
                ("Trail Master", 1799, ["grippy", "durable", "all terrain"]),
                ("Ridge Walker", 1299, ["lightweight", "breathable", "day hike"]),
                ("Summit X", 2499, ["waterproof", "premium", "mountaineering"]),
            ],
            "Decathlon": [
                ("Trek 100", 999, ["budget friendly", "lightweight", "beginner"]),
                ("Trek 500", 1999, ["waterproof", "mid ankle", "versatile"]),
                ("Trek 700", 2799, ["waterproof", "insulated", "premium"]),
                ("NH100", 799, ["budget friendly", "entry level", "casual hike"]),
                ("MH500", 1499, ["waterproof", "mid range", "all terrain"]),
            ],
            "Adidas": [
                ("Terrex AX4", 2499, ["continental sole", "waterproof", "durable"]),
                ("Terrex Swift R3", 2999, ["gore-tex", "lightweight", "fast hiking"]),
                ("Terrex Free Hiker", 3999, ["boost cushion", "premium", "waterproof"]),
                ("Terrex Trailmaker", 1999, ["versatile", "grippy", "trail"]),
                ("Terrex Eastrail", 1599, ["budget friendly", "all terrain", "durable"]),
            ],
            "Salomon": [
                ("X Ultra 4", 3499, ["waterproof", "lightweight", "stability"]),
                ("Quest 4 GTX", 4499, ["gore-tex", "ankle support", "premium"]),
                ("Speedcross 6", 2999, ["trail grip", "aggressive tread", "off road"]),
                ("Outpulse GTX", 2499, ["waterproof", "cushioned", "day hike"]),
                ("XA Pro 3D V9", 2799, ["all terrain", "durable", "versatile"]),
            ],
            "Merrell": [
                ("Moab 3 GTX", 3199, ["waterproof", "vibram sole", "classic"]),
                ("MQM 3 GTX", 2899, ["lightweight", "waterproof", "fast hiking"]),
                ("Chameleon 8", 2499, ["versatile", "breathable", "all terrain"]),
                ("Thermo Snowdrift", 3499, ["insulated", "waterproof", "winter"]),
                ("Trail Glove 7", 1999, ["barefoot feel", "minimalist", "trail"]),
            ],
        },
        "sizes": ["6", "7", "8", "9", "10", "11"],
        "colors": ["brown", "green", "grey", "black", "olive", "tan", "khaki"],
    },
    "casual sneakers": {
        "brands": {
            "Nike": [
                ("Air Force 1", 2899, ["classic", "leather", "street style"]),
                ("Dunk Low", 2499, ["retro", "leather", "street style"]),
                ("Air Max 90", 3199, ["air cushion", "iconic", "comfortable"]),
                ("Blazer Mid", 2299, ["vintage", "canvas", "high top"]),
                ("Court Vision", 1499, ["classic", "leather", "everyday"]),
                ("Air Max 97", 3499, ["air cushion", "futuristic", "premium"]),
                ("Jordan 1 Low", 2999, ["iconic", "leather", "basketball heritage"]),
                ("Waffle One", 1899, ["retro", "lightweight", "comfortable"]),
            ],
            "Adidas": [
                ("Stan Smith", 2499, ["classic", "leather", "minimalist"]),
                ("Superstar", 2299, ["shell toe", "iconic", "street style"]),
                ("Gazelle", 1999, ["suede", "retro", "classic"]),
                ("Forum Low", 2699, ["basketball heritage", "retro", "leather"]),
                ("Samba OG", 2199, ["indoor soccer", "classic", "gum sole"]),
                ("NMD R1", 2899, ["boost cushion", "modern", "comfortable"]),
                ("Continental 80", 1799, ["retro", "leather", "minimalist"]),
                ("Campus 00s", 2099, ["suede", "retro", "casual"]),
            ],
            "Puma": [
                ("Suede Classic", 1899, ["suede", "retro", "street style"]),
                ("RS-X", 2299, ["chunky", "retro", "running inspired"]),
                ("Clyde All-Pro", 2499, ["basketball heritage", "leather", "classic"]),
                ("Palermo", 1699, ["retro", "suede", "terrace style"]),
                ("Caven 2.0", 1299, ["budget friendly", "leather", "everyday"]),
            ],
            "Converse": [
                ("Chuck Taylor All Star", 1499, ["canvas", "iconic", "high top"]),
                ("Chuck 70", 1999, ["premium canvas", "vintage", "classic"]),
                ("One Star Pro", 1799, ["suede", "skate", "retro"]),
                ("Jack Purcell", 1699, ["canvas", "minimalist", "classic"]),
                ("Run Star Hike", 2499, ["platform", "chunky", "bold"]),
            ],
            "Vans": [
                ("Old Skool", 1699, ["canvas", "suede", "skate"]),
                ("Authentic", 1299, ["canvas", "classic", "simple"]),
                ("Sk8-Hi", 1899, ["high top", "canvas", "skate"]),
                ("Era", 1399, ["padded collar", "skate", "retro"]),
                ("Slip-On", 1199, ["laceless", "canvas", "easy wear"]),
            ],
        },
        "sizes": ["6", "7", "8", "9", "10", "11", "12"],
        "colors": ["white", "black", "blue", "red", "green", "cream", "navy", "burgundy"],
    },
    "jackets": {
        "brands": {
            "Nike": [
                ("Windrunner Jacket", 1499, ["windproof", "lightweight", "packable"]),
                ("Therma-FIT Repel", 2999, ["insulated", "water repellent", "warm"]),
                ("Storm-FIT ADV", 3999, ["waterproof", "breathable", "premium"]),
                ("Club Fleece Hoodie", 1299, ["fleece", "warm", "casual"]),
                ("Sportswear Tech Fleece", 2499, ["tech fleece", "lightweight", "warm"]),
            ],
            "Adidas": [
                ("Terrex Rain Jacket", 2499, ["waterproof", "breathable", "hiking"]),
                ("BSC Insulated Jacket", 1999, ["insulated", "warm", "winter"]),
                ("Own The Run Jacket", 1699, ["running", "reflective", "lightweight"]),
                ("Essentials Down Jacket", 2999, ["down fill", "warm", "packable"]),
                ("Tiro Track Jacket", 1299, ["training", "lightweight", "athletic"]),
            ],
            "Woodland": [
                ("Thermal Trek Jacket", 1299, ["warm", "insulated", "trekking"]),
                ("Alpine Parka", 2499, ["waterproof", "insulated", "heavy duty"]),
                ("Trail Softshell", 1799, ["windproof", "flexible", "breathable"]),
                ("Expedition Down", 3499, ["down fill", "extreme cold", "premium"]),
                ("Forest Fleece", 999, ["fleece", "lightweight", "layering"]),
            ],
            "Decathlon": [
                ("Rain Jacket", 799, ["waterproof", "lightweight", "budget friendly"]),
                ("Trek Padded Jacket", 1499, ["insulated", "trekking", "warm"]),
                ("Softshell Jacket", 1199, ["windproof", "stretchy", "breathable"]),
                ("Down Jacket MT500", 1999, ["down fill", "lightweight", "packable"]),
                ("Fleece MH100", 599, ["fleece", "budget friendly", "layering"]),
            ],
            "Columbia": [
                ("Watertight II", 2299, ["waterproof", "packable", "versatile"]),
                ("Powder Lite Hooded", 2999, ["insulated", "thermal reflective", "warm"]),
                ("Silver Ridge Fleece", 1799, ["fleece", "quick dry", "comfortable"]),
                ("Bugaboo II Interchange", 3999, ["3-in-1", "waterproof", "versatile"]),
                ("Steens Mountain", 1499, ["fleece", "classic", "warm"]),
            ],
            "The North Face": [
                ("Thermoball Eco", 3499, ["synthetic insulation", "packable", "warm"]),
                ("Resolve 2", 2499, ["waterproof", "breathable", "versatile"]),
                ("Denali Fleece", 2999, ["fleece", "iconic", "warm"]),
                ("McMurdo Parka", 4999, ["down fill", "extreme cold", "premium"]),
                ("Venture 2", 1999, ["waterproof", "lightweight", "packable"]),
            ],
        },
        "sizes": ["S", "M", "L", "XL", "XXL"],
        "colors": ["black", "blue", "olive", "grey", "red", "navy", "yellow", "green"],
    },
    "backpacks": {
        "brands": {
            "Nike": [
                ("Brasilia Training", 999, ["gym", "training", "laptop compartment"]),
                ("Hayward Backpack", 1299, ["everyday", "padded straps", "spacious"]),
                ("Heritage Backpack", 899, ["compact", "casual", "lightweight"]),
                ("Elemental Premium", 1499, ["premium", "laptop sleeve", "organized"]),
                ("Hoops Elite", 1799, ["basketball", "large", "durable"]),
            ],
            "Adidas": [
                ("Classic 3-Stripes", 999, ["everyday", "laptop sleeve", "classic"]),
                ("Power Backpack", 1199, ["training", "spacious", "durable"]),
                ("Prime Backpack", 799, ["compact", "lightweight", "budget friendly"]),
                ("Terrex Multi", 1999, ["hiking", "hydration compatible", "durable"]),
                ("Linear Backpack", 699, ["budget friendly", "compact", "everyday"]),
            ],
            "Woodland": [
                ("Expedition 40L", 1799, ["trekking", "rain cover", "ergonomic"]),
                ("Summit 60L", 2499, ["mountaineering", "large", "frame pack"]),
                ("Trail 25L", 1299, ["day hike", "lightweight", "compact"]),
                ("Urban Commuter", 999, ["laptop compartment", "everyday", "water resistant"]),
                ("Explorer 50L", 2199, ["trekking", "rain cover", "ventilated back"]),
            ],
            "Decathlon": [
                ("Day Hike 20L", 599, ["day hike", "lightweight", "budget friendly"]),
                ("Trek 40L Easyfit", 1799, ["trekking", "adjustable", "rain cover"]),
                ("NH Arpenaz 10L", 399, ["ultra compact", "budget friendly", "light"]),
                ("MH500 30L", 1299, ["hiking", "ventilated", "comfortable"]),
                ("Travel 500 70L", 2499, ["travel", "lockable", "large"]),
            ],
            "Wildcraft": [
                ("Rucksack 45L", 1599, ["trekking", "rain cover", "sturdy"]),
                ("Urbana 30L", 1199, ["laptop compartment", "everyday", "padded"]),
                ("Trail 35L", 1399, ["hiking", "lightweight", "breathable back"]),
                ("Campus Pack", 899, ["student", "laptop sleeve", "compact"]),
                ("Summit 55L", 1999, ["trekking", "large", "ergonomic"]),
            ],
        },
        "sizes": ["10L", "15L", "20L", "25L", "30L", "35L", "40L", "50L", "60L"],
        "colors": ["black", "blue", "green", "grey", "red", "navy", "orange"],
    },
    "sports wear": {
        "brands": {
            "Nike": [
                ("Dri-FIT T-Shirt", 599, ["moisture wicking", "breathable", "training"]),
                ("Pro Compression Top", 899, ["compression", "base layer", "support"]),
                ("Dri-FIT Shorts", 699, ["moisture wicking", "lightweight", "running"]),
                ("Flex Stride Shorts", 999, ["flexible", "lined", "running"]),
                ("One Leggings", 1299, ["high waist", "supportive", "training"]),
                ("Pro Tank Top", 799, ["sleeveless", "breathable", "gym"]),
                ("Dri-FIT Polo", 1199, ["collar", "moisture wicking", "sport"]),
                ("Therma Training Pants", 1499, ["warm", "fleece lined", "training"]),
            ],
            "Adidas": [
                ("Aeroready T-Shirt", 649, ["moisture wicking", "breathable", "training"]),
                ("Techfit Compression", 999, ["compression", "base layer", "performance"]),
                ("Own The Run Shorts", 799, ["running", "lightweight", "reflective"]),
                ("Designed 4 Training Shorts", 899, ["training", "stretchy", "comfortable"]),
                ("Tiro Track Pants", 1199, ["training", "slim fit", "classic"]),
                ("Freelift Tank", 699, ["sleeveless", "breathable", "gym"]),
                ("Essentials Polo", 999, ["collar", "casual sport", "classic"]),
            ],
            "Puma": [
                ("Training Tank Top", 499, ["sleeveless", "breathable", "gym"]),
                ("Run Favorite T-Shirt", 599, ["moisture wicking", "running", "lightweight"]),
                ("TeamGOAL Shorts", 699, ["training", "comfortable", "sport"]),
                ("Active Woven Pants", 999, ["lightweight", "training", "versatile"]),
                ("Performance Tights", 1199, ["compression", "support", "running"]),
            ],
            "Under Armour": [
                ("Tech 2.0 T-Shirt", 799, ["moisture wicking", "anti odor", "training"]),
                ("HeatGear Compression", 1099, ["compression", "cooling", "base layer"]),
                ("Launch Shorts", 899, ["running", "lightweight", "quick dry"]),
                ("Streaker Singlet", 699, ["running", "sleeveless", "ultralight"]),
                ("Rival Fleece Jogger", 1399, ["fleece", "warm", "casual training"]),
            ],
            "Reebok": [
                ("CrossFit Tee", 699, ["crossfit", "durable", "breathable"]),
                ("Training Shorts", 599, ["training", "lightweight", "flexible"]),
                ("Workout Compression", 899, ["compression", "support", "performance"]),
                ("Running Tank", 499, ["sleeveless", "lightweight", "running"]),
                ("Speed Tights", 999, ["compression", "running", "reflective"]),
            ],
        },
        "sizes": ["XS", "S", "M", "L", "XL", "XXL"],
        "colors": ["black", "white", "grey", "blue", "red", "green", "navy"],
    },
    "formal shoes": {
        "brands": {
            "Clarks": [
                ("Tilden Cap Oxford", 2999, ["leather", "formal", "cushioned"]),
                ("Whiddon Plain", 2499, ["leather", "classic", "ortholite"]),
                ("Howard Wing", 3499, ["brogue", "leather", "premium"]),
                ("Tilden Walk", 2799, ["leather", "lace up", "cushioned"]),
                ("Atticus LT Lace", 3199, ["leather", "lightweight", "modern"]),
            ],
            "Hush Puppies": [
                ("Mall Walker", 2299, ["leather", "comfortable", "cushioned"]),
                ("Gil Oxford", 1999, ["leather", "classic", "formal"]),
                ("Shepsky Derby", 2499, ["leather", "modern", "padded"]),
                ("Advice PT Derby", 1799, ["leather", "budget friendly", "formal"]),
                ("Turner MT Oxford", 2699, ["leather", "premium", "slip resistant"]),
            ],
            "Red Tape": [
                ("Classic Derby", 1299, ["leather", "formal", "budget friendly"]),
                ("Monk Strap", 1499, ["leather", "single strap", "modern"]),
                ("Brogue Oxford", 1699, ["brogue", "leather", "classic"]),
                ("Slip On Formal", 1199, ["laceless", "leather", "easy wear"]),
                ("Cap Toe Oxford", 1399, ["leather", "classic", "formal"]),
            ],
            "Louis Philippe": [
                ("Classic Oxford", 3499, ["leather", "premium", "handcrafted"]),
                ("Derby Lace Up", 2999, ["leather", "formal", "cushioned"]),
                ("Monk Strap", 3299, ["leather", "elegant", "modern"]),
                ("Loafer", 2799, ["leather", "slip on", "comfortable"]),
                ("Brogue Wing Tip", 3699, ["brogue", "leather", "premium"]),
            ],
        },
        "sizes": ["6", "7", "8", "9", "10", "11"],
        "colors": ["black", "brown", "tan", "burgundy", "dark brown", "cognac"],
    },
    "sandals": {
        "brands": {
            "Nike": [
                ("Benassi Slide", 699, ["slide", "lightweight", "casual"]),
                ("Canyon Sandal", 1299, ["outdoor", "strappy", "grippy"]),
                ("Victori One Slide", 799, ["slide", "cushioned", "recovery"]),
                ("ACG Air Deschutz", 1999, ["trail", "adventure", "durable"]),
                ("Offcourt Slide", 899, ["recovery", "cushioned", "comfortable"]),
            ],
            "Adidas": [
                ("Adilette Slide", 799, ["slide", "classic", "lightweight"]),
                ("Adilette Comfort", 999, ["cloudfoam", "cushioned", "slide"]),
                ("Terrex Cyprex Ultra", 1499, ["outdoor", "water friendly", "grippy"]),
                ("Adilette Aqua", 599, ["pool", "lightweight", "budget friendly"]),
                ("Comfort Flip Flop", 699, ["flip flop", "cushioned", "casual"]),
            ],
            "Puma": [
                ("Leadcat 2.0", 599, ["slide", "casual", "lightweight"]),
                ("Softride Slide", 899, ["cushioned", "recovery", "comfortable"]),
                ("Royalcat Comfort", 699, ["slide", "padded", "everyday"]),
            ],
            "Woodland": [
                ("Leather Sandal", 1299, ["leather", "durable", "outdoor"]),
                ("Velcro Trek Sandal", 999, ["adjustable", "trekking", "grippy"]),
                ("Floater Sandal", 799, ["casual", "lightweight", "everyday"]),
            ],
            "Bata": [
                ("Comfort Sandal", 499, ["budget friendly", "comfortable", "everyday"]),
                ("Leather Chappal", 699, ["leather", "classic", "durable"]),
                ("Sports Sandal", 599, ["sporty", "velcro", "casual"]),
                ("Outdoor Sandal", 799, ["grippy", "durable", "adventure"]),
            ],
        },
        "sizes": ["6", "7", "8", "9", "10", "11"],
        "colors": ["black", "brown", "blue", "white", "grey", "red", "olive"],
    },
    "gym equipment": {
        "brands": {
            "Nike": [
                ("Training Gloves", 499, ["grip", "wrist support", "breathable"]),
                ("Resistance Band Set", 699, ["multi level", "portable", "versatile"]),
                ("Speed Rope", 399, ["skipping", "cardio", "lightweight"]),
                ("Yoga Mat", 999, ["non slip", "cushioned", "durable"]),
                ("Training Belt", 799, ["support", "weight lifting", "padded"]),
            ],
            "Decathlon": [
                ("Hex Dumbbell 5kg", 599, ["cast iron", "hex shape", "non roll"]),
                ("Hex Dumbbell 10kg", 999, ["cast iron", "hex shape", "non roll"]),
                ("Kettlebell 8kg", 799, ["cast iron", "vinyl coated", "full body"]),
                ("Pull Up Bar", 699, ["doorway mount", "multi grip", "portable"]),
                ("Ab Roller", 399, ["core", "portable", "beginner"]),
                ("Foam Roller", 499, ["recovery", "massage", "portable"]),
                ("Resistance Tube Set", 599, ["multi level", "handles", "versatile"]),
                ("Yoga Mat 5mm", 499, ["non slip", "budget friendly", "lightweight"]),
            ],
            "Boldfit": [
                ("Resistance Bands Set", 499, ["latex", "multi level", "portable"]),
                ("Hand Gripper", 199, ["forearm", "adjustable", "compact"]),
                ("Skipping Rope", 299, ["ball bearing", "cardio", "adjustable"]),
                ("Push Up Board", 599, ["multi angle", "color coded", "portable"]),
                ("Wrist Wraps", 299, ["support", "weight lifting", "velcro"]),
            ],
            "Cult Sport": [
                ("Adjustable Dumbbell", 1999, ["adjustable weight", "compact", "versatile"]),
                ("Yoga Mat Premium", 799, ["TPE material", "non slip", "thick"]),
                ("Kettlebell Vinyl 12kg", 1199, ["vinyl coated", "full body", "durable"]),
                ("Battle Rope 9m", 1499, ["cardio", "full body", "heavy"]),
                ("Weight Plate 10kg", 899, ["cast iron", "standard hole", "durable"]),
            ],
        },
        "sizes": ["one size"],
        "colors": ["black", "grey", "blue", "red", "green", "purple", "orange"],
    },
    "watches": {
        "brands": {
            "Casio": [
                ("G-Shock GA-2100", 3999, ["shock resistant", "analog digital", "tough"]),
                ("G-Shock DW-5600", 2999, ["digital", "classic", "water resistant"]),
                ("Edifice Chronograph", 4499, ["chronograph", "steel", "sporty"]),
                ("A168WA Vintage", 999, ["digital", "retro", "lightweight"]),
                ("F-91W Classic", 499, ["digital", "budget friendly", "lightweight"]),
            ],
            "Titan": [
                ("Octane Chronograph", 2499, ["chronograph", "leather strap", "classic"]),
                ("Edge Ceramic", 3999, ["ceramic", "slim", "premium"]),
                ("Karishma Analog", 1299, ["analog", "formal", "leather strap"]),
                ("Neo Analog", 999, ["analog", "casual", "everyday"]),
                ("Workwear Steel", 1799, ["steel", "formal", "durable"]),
            ],
            "Fastrack": [
                ("Reflex Play", 1999, ["smartwatch", "fitness tracking", "touch screen"]),
                ("Casual Analog", 799, ["analog", "casual", "youth"]),
                ("Bold Digital", 699, ["digital", "sporty", "youth"]),
                ("Minimalist Analog", 1199, ["analog", "minimal", "leather strap"]),
                ("Adventure Sport", 1499, ["sport", "water resistant", "rugged"]),
            ],
            "Noise": [
                ("ColorFit Pro 4", 1999, ["smartwatch", "amoled", "fitness"]),
                ("ColorFit Pulse 2", 1299, ["smartwatch", "spo2", "budget friendly"]),
                ("ColorFit Ultra 3", 2499, ["smartwatch", "premium", "gps"]),
                ("NoiseFit Halo", 1799, ["smartwatch", "round dial", "bluetooth calling"]),
                ("ColorFit Nav", 1499, ["smartwatch", "gps", "fitness"]),
            ],
            "Boat": [
                ("Wave Call", 1299, ["smartwatch", "bluetooth calling", "fitness"]),
                ("Storm Call 2", 1499, ["smartwatch", "round dial", "premium"]),
                ("Xtend Sport", 999, ["smartwatch", "fitness", "budget friendly"]),
                ("Wave Lite", 799, ["smartwatch", "lightweight", "budget friendly"]),
                ("Enigma", 1799, ["smartwatch", "amoled", "premium"]),
            ],
        },
        "sizes": ["one size"],
        "colors": ["black", "silver", "gold", "blue", "green", "grey", "rose gold"],
    },
}


def generate_products():
    """Generate ~500 products from the catalog templates with color variants."""
    products = []
    color_index = 0

    for category, data in CATALOG.items():
        sizes = data["sizes"]
        colors = data["colors"]

        for brand, models_list in data["brands"].items():
            for model_name, price, attributes in models_list:
                # Create 1 or 2 color variants per model to reach ~500
                num_variants = 2 if len(products) < 470 else 1
                for v in range(num_variants):
                    color = colors[(color_index + v) % len(colors)]

                    # Pick a subset of sizes
                    if len(sizes) > 4:
                        product_sizes = sizes[1:5]
                    else:
                        product_sizes = sizes

                    # Generate SKU
                    brand_code = brand[:2].upper()
                    cat_code = category[:3].upper()
                    idx = len(products) + 1
                    sku = f"{brand_code}-{cat_code}-{idx:03d}"

                    # Slight price variation for second color
                    variant_price = price if v == 0 else price + (100 if price > 1000 else 50)

                    name_suffix = f" ({color.title()})" if v > 0 else ""

                    products.append({
                        "tenant_id": TENANT_ID,
                        "sku": sku,
                        "name": f"{brand} {model_name}{name_suffix}",
                        "category": category,
                        "brand": brand,
                        "price": variant_price,
                        "size": product_sizes,
                        "color": color,
                        "attributes": attributes,
                        "description": f"{brand} {model_name} in {color} - {', '.join(attributes)}. Perfect for {category}."
                    })

                color_index += 1

    return products


def ingest_via_api(products):
    """Ingest products via the bulk API endpoint in batches of 100."""
    total = len(products)
    ingested = 0
    failed = 0

    for i in range(0, total, 100):
        batch = products[i:i + 100]
        payload = json.dumps({
            "tenant_id": TENANT_ID,
            "products": batch
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{BASE_URL}/api/v1/ingest/products/bulk",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode())
                ingested += result["ingested"]
                failed += result["failed"]
                print(f"  Batch {i // 100 + 1}: {result['ingested']} ingested, {result['failed']} failed")
                if result.get("errors"):
                    for err in result["errors"]:
                        print(f"    Error: {err['sku']} - {err['reason']}")
        except Exception as e:
            print(f"  Batch {i // 100 + 1} FAILED: {e}")
            failed += len(batch)

    return ingested, failed


def main():
    tenant = sys.argv[1] if len(sys.argv) > 1 else TENANT_ID

    products = generate_products()
    print(f"Generated {len(products)} products across {len(CATALOG)} categories")
    print(f"Ingesting into tenant: {tenant}\n")

    ingested, failed = ingest_via_api(products)

    print(f"\nDone: {ingested} ingested, {failed} failed")

    # Check collection
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/v1/ingest/collection/{tenant}")
        with urllib.request.urlopen(req) as resp:
            info = json.loads(resp.read().decode())
            print(f"Collection: {info['name']}, Points: {info['points_count']}")
    except Exception as e:
        print(f"Could not fetch collection info: {e}")


if __name__ == "__main__":
    main()
