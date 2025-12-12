#!/usr/bin/env python3
"""
Check logos for wrong colors by comparing against known brand colors.
"""

import os
import sys
from pathlib import Path
from PIL import Image
import numpy as np
from collections import Counter
import math

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import LOGOS_DIR as CONFIG_LOGOS_DIR

LOGOS_DIR = str(CONFIG_LOGOS_DIR)

# Brand colors from brandcolors.net - hex codes for major brands
# Format: 'Brand_Name': ['#hex1', '#hex2', ...]  (primary colors first)
BRAND_COLORS = {
    # Hotels
    'Hilton': ['#104c97', '#002855'],  # Blue
    'Marriott': ['#a50034', '#1c1c1c'],  # Burgundy/red
    'Hyatt': ['#d4a76a', '#1e3f5a'],  # Gold, navy
    'IHG': ['#1e4d2b', '#007a53'],  # Green
    'Wyndham': ['#003865', '#00a5b5'],  # Blue
    'Choice_Hotels': ['#003057', '#00aeef'],  # Blue
    'Best_Western': ['#003366', '#ffcc00'],  # Blue, gold
    'Radisson': ['#003087', '#d4a661'],  # Blue, gold
    'Four_Seasons': ['#b9975b', '#1a1a1a'],  # Gold, black
    'Ritz_Carlton': ['#0c2340', '#b9975b'],  # Navy, gold
    'Sheraton': ['#1c1c1c', '#8b734b'],  # Black, brown
    'Westin': ['#003057', '#8c8279'],  # Navy, gray
    'W_Hotels': ['#000000'],  # Black
    'Ace_Hotels': ['#000000', '#ff0000'],  # Black, red
    'Accor': ['#003580', '#d4af37'],  # Blue, gold

    # Tech
    'Amazon': ['#ff9900', '#146eb4'],  # Orange, blue
    'Google': ['#4285f4', '#ea4335', '#fbbc05', '#34a853'],  # Blue, red, yellow, green
    'Microsoft': ['#00a4ef', '#7fba00', '#f25022', '#ffb900'],  # Blue, green, red, yellow
    'Apple': ['#000000', '#555555'],  # Black, gray
    'Meta': ['#0668e1', '#0866ff'],  # Blue (Facebook blue)
    'Facebook': ['#1877f2'],  # Blue
    'Netflix': ['#e50914', '#000000'],  # Red, black
    'Adobe': ['#ff0000', '#fbb034'],  # Red
    'Oracle': ['#f80000', '#312d2a'],  # Red, dark
    'IBM': ['#006699', '#000000'],  # Blue, black
    'Intel': ['#0071c5', '#000000'],  # Blue, black
    'Cisco': ['#049fd9', '#00bceb'],  # Blue, cyan
    'SAP': ['#008fd3', '#004b87'],  # Blue
    'Salesforce': ['#00a1e0', '#1798c1'],  # Blue
    'VMware': ['#696566', '#78be20'],  # Gray, green
    'Dell': ['#007db8', '#000000'],  # Blue, black
    'HP': ['#0096d6', '#000000'],  # Blue, black
    'Lenovo': ['#e2231a', '#000000'],  # Red, black
    'Samsung': ['#1428a0', '#000000'],  # Blue, black
    'LG': ['#a50034', '#6b6b6b'],  # Red, gray
    'Sony': ['#000000'],  # Black
    'Panasonic': ['#0f58a8', '#000000'],  # Blue, black
    'Toshiba': ['#ff0000', '#000000'],  # Red, black
    'Fujitsu': ['#ff0000', '#000000'],  # Red, black
    'Hitachi': ['#e60012', '#231815'],  # Red, dark
    'NEC': ['#003399', '#cccccc'],  # Blue, gray

    # Retail
    'Walmart': ['#0071ce', '#ffc220'],  # Blue, yellow
    'Target': ['#cc0000', '#ffffff'],  # Red, white
    'Costco': ['#005daa', '#e31837'],  # Blue, red
    'Kroger': ['#d32f2f', '#1952a1'],  # Red, blue
    'Walgreens': ['#e31837', '#ffffff'],  # Red, white
    'CVS': ['#cc0000', '#ffffff'],  # Red, white
    'Home_Depot': ['#f96302', '#000000'],  # Orange, black
    'Lowes': ['#004990', '#000000'],  # Blue, black
    'IKEA': ['#0051ba', '#ffda1a'],  # Blue, yellow
    'Macys': ['#e21a2c', '#000000'],  # Red, black
    'Nordstrom': ['#000000'],  # Black
    'JCPenney': ['#be1d2d', '#000000'],  # Red, black
    'Kohls': ['#000000', '#e3242b'],  # Black, red
    'TJ_Maxx': ['#cc0000', '#ffffff'],  # Red
    'Ross': ['#0033a0', '#c8102e'],  # Blue, red
    'Marshalls': ['#005bab', '#c8102e'],  # Blue, red
    'Dollar_General': ['#ffcc00', '#000000'],  # Yellow, black
    'Dollar_Tree': ['#00aa4f', '#000000'],  # Green, black
    'Family_Dollar': ['#ff6600', '#ffffff'],  # Orange
    'Aldi': ['#00529b', '#f6a800'],  # Blue, yellow/orange
    'Lidl': ['#0050aa', '#fff000'],  # Blue, yellow
    'Trader_Joes': ['#c8102e', '#ffffff'],  # Red, white
    'Whole_Foods': ['#00674b', '#ffffff'],  # Green, white
    'Sprouts': ['#6cc24a', '#ffffff'],  # Green
    'Publix': ['#3a8b3b', '#ffffff'],  # Green
    'Safeway': ['#e21836', '#ffffff'],  # Red
    'Albertsons': ['#0073cf', '#d9272d'],  # Blue, red
    'Albertsons_Companies': ['#0073cf', '#d9272d'],  # Blue, red
    'Wegmans': ['#cb2e26', '#000000'],  # Red
    'HEB': ['#cc0000', '#ffffff'],  # Red
    'Giant': ['#e11b22', '#ffffff'],  # Red
    'Stop_Shop': ['#a21d21', '#ffffff'],  # Red
    'Rite_Aid': ['#004b87', '#ed1b24'],  # Blue, red
    'Starbucks': ['#00704a', '#1e3932'],  # Green
    'Dunkin': ['#ff671f', '#e11383'],  # Orange, pink
    'McDonalds': ['#ffc72c', '#da291c'],  # Yellow, red
    'Burger_King': ['#d62300', '#f5ebdc'],  # Red, cream
    'Wendys': ['#e2203d', '#199fda'],  # Red, blue
    'Subway': ['#009743', '#ffc600'],  # Green, yellow
    'Chipotle': ['#441500', '#a81612'],  # Brown, red
    'Chick_fil_A': ['#e51636', '#ffffff'],  # Red
    'Taco_Bell': ['#702082', '#a77bca'],  # Purple
    'Pizza_Hut': ['#ee3a24', '#00a160'],  # Red, green
    'Dominos': ['#006491', '#e31837'],  # Blue, red
    'Papa_Johns': ['#006e3f', '#c8102e'],  # Green, red
    'KFC': ['#b40000', '#ffffff'],  # Red
    'Popeyes': ['#f26522', '#000000'],  # Orange, black

    # Banks & Finance
    'JPMorgan': ['#117aca', '#000000'],  # Blue, black
    'JPMorgan_Chase': ['#117aca', '#000000'],  # Blue, black
    'Chase': ['#117aca', '#000000'],  # Blue
    'Bank_of_America': ['#012169', '#e31837'],  # Blue, red
    'Wells_Fargo': ['#d71e28', '#ffcd41'],  # Red, yellow
    'Citibank': ['#003b70', '#e31837'],  # Blue, red
    'Citi': ['#003b70', '#e31837'],  # Blue, red
    'Goldman_Sachs': ['#7399c6', '#ffffff'],  # Blue, white
    'Morgan_Stanley': ['#002f5f', '#ffffff'],  # Navy
    'Capital_One': ['#004879', '#d03027'],  # Blue, red
    'American_Express': ['#002663', '#4d4f53'],  # Blue, gray
    'Visa': ['#1a1f71', '#f7b600'],  # Blue, yellow
    'Mastercard': ['#eb001b', '#f79e1b'],  # Red, orange
    'PayPal': ['#003087', '#009cde'],  # Blue, light blue
    'Stripe': ['#635bff', '#000000'],  # Purple, black
    'Square': ['#006aff', '#000000'],  # Blue, black
    'Fidelity': ['#4c8a2a', '#000000'],  # Green, black
    'Charles_Schwab': ['#00a0df', '#000000'],  # Blue, black
    'TD_Bank': ['#34b233', '#ffffff'],  # Green
    'PNC': ['#ff6600', '#ffffff'],  # Orange
    'US_Bank': ['#0f2b5b', '#d0261d'],  # Navy, red
    'Truist': ['#8031a7', '#ffffff'],  # Purple
    'HSBC': ['#db0011', '#ffffff'],  # Red
    'Barclays': ['#00aeef', '#ffffff'],  # Blue
    'Deutsche_Bank': ['#001f47', '#ffffff'],  # Navy
    'UBS': ['#e60000', '#ffffff'],  # Red
    'Credit_Suisse': ['#002855', '#ffffff'],  # Navy
    'BNP_Paribas': ['#00915a', '#ffffff'],  # Green

    # Healthcare
    'Kaiser_Permanente': ['#004b87', '#bc8b2c'],  # Blue, gold
    'Kaiser': ['#004b87', '#bc8b2c'],  # Blue, gold
    'UnitedHealth': ['#002677', '#00bfb3'],  # Blue, teal
    'CVS_Health': ['#cc0000', '#ffffff'],  # Red
    'Cigna': ['#006699', '#ee7203'],  # Blue, orange
    'Anthem': ['#003b73', '#88d1f1'],  # Blue
    'Aetna': ['#d20962', '#7ac143'],  # Pink, green
    'Humana': ['#009a44', '#ffffff'],  # Green
    'Blue_Cross': ['#0072ce', '#ffffff'],  # Blue
    'Blue_Shield': ['#0072ce', '#ffffff'],  # Blue
    'Ascension': ['#004b87', '#ffffff'],  # Blue
    'Ascension_Health': ['#004b87', '#ffffff'],  # Blue
    'HCA': ['#003d7c', '#ffffff'],  # Blue
    'HCA_Healthcare': ['#003d7c', '#ffffff'],  # Blue
    'CommonSpirit': ['#003087', '#ffffff'],  # Blue
    'Providence': ['#630031', '#ffffff'],  # Maroon
    'Sutter_Health': ['#005eb8', '#ffffff'],  # Blue
    'Dignity_Health': ['#a50034', '#ffffff'],  # Red
    'Trinity_Health': ['#003a70', '#ffffff'],  # Navy
    'Advent_Health': ['#0077c8', '#e35205'],  # Blue, orange
    'Adventist': ['#003c71', '#ffffff'],  # Navy
    'Adventist_Hospital': ['#003c71', '#ffffff'],  # Navy
    'Cleveland_Clinic': ['#006a4d', '#ffffff'],  # Green
    'Mayo_Clinic': ['#0057b8', '#ffffff'],  # Blue
    'Johns_Hopkins': ['#002d72', '#cf4520'],  # Blue, orange
    'Mass_General': ['#003478', '#ffffff'],  # Blue
    'UCSF': ['#052049', '#ffffff'],  # Navy
    'UCLA_Health': ['#2774ae', '#ffd100'],  # Blue, gold
    'Stanford_Health': ['#8c1515', '#ffffff'],  # Cardinal red
    'Mount_Sinai': ['#221f73', '#ffffff'],  # Purple/navy
    'NYU_Langone': ['#57068c', '#ffffff'],  # Purple
    'NewYork_Presbyterian': ['#ec1c24', '#ffffff'],  # Red

    # Government
    'GSA': ['#003366', '#007eb5'],  # Dark blue, blue - General Services Administration
    'General_Services_Administration': ['#003366', '#007eb5'],  # Blue
    'US_Government': ['#003366', '#ffffff'],  # Blue
    'Department_Of_Defense': ['#003366', '#ffffff'],  # Navy blue
    'US_Postal_Service': ['#004b87', '#cc0000'],  # Blue, red
    'USPS': ['#004b87', '#cc0000'],  # Blue, red
    'US_Army': ['#4b5320', '#ffd700'],  # Army green, gold
    'US_Navy': ['#003b4f', '#ffd700'],  # Navy blue, gold
    'US_Air_Force': ['#00308f', '#ffffff'],  # Blue
    'FBI': ['#003366', '#ffffff'],  # Navy
    'CIA': ['#003366', '#ffffff'],  # Navy
    'NASA': ['#0b3d91', '#fc3d21'],  # Blue, red
    'IRS': ['#003366', '#ffffff'],  # Navy
    'Social_Security': ['#003366', '#ffffff'],  # Navy
    'Veterans_Affairs': ['#003366', '#ffffff'],  # Navy
    'VA': ['#003366', '#ffffff'],  # Navy

    # Airlines
    'Delta': ['#003366', '#c8102e'],  # Navy, red
    'United': ['#002244', '#0033a0'],  # Navy, blue
    'American_Airlines': ['#0d6efd', '#c8102e'],  # Blue, red
    'Southwest': ['#f9b612', '#304cb2'],  # Yellow, blue
    'JetBlue': ['#003876', '#ffffff'],  # Blue
    'Alaska_Airlines': ['#01426a', '#ffffff'],  # Navy
    'Spirit': ['#f7e014', '#000000'],  # Yellow, black
    'Frontier': ['#004225', '#ffffff'],  # Green

    # Auto
    'Ford': ['#003478', '#ffffff'],  # Blue
    'GM': ['#0170ce', '#ffffff'],  # Blue
    'General_Motors': ['#0170ce', '#ffffff'],  # Blue
    'Chevrolet': ['#d1a319', '#ffffff'],  # Gold
    'Toyota': ['#eb0a1e', '#ffffff'],  # Red
    'Honda': ['#cc0000', '#ffffff'],  # Red
    'Nissan': ['#c3002f', '#ffffff'],  # Red
    'BMW': ['#0066b1', '#ffffff'],  # Blue
    'Mercedes': ['#00adef', '#333333'],  # Blue, dark
    'Mercedes_Benz': ['#00adef', '#333333'],  # Blue, dark
    'Audi': ['#bb0a30', '#000000'],  # Red, black
    'Volkswagen': ['#001e50', '#ffffff'],  # Navy
    'Porsche': ['#000000', '#d5001c'],  # Black, red
    'Tesla': ['#cc0000', '#ffffff'],  # Red
    'Uber': ['#000000', '#ffffff'],  # Black
    'Lyft': ['#ff00bf', '#ffffff'],  # Pink
    'Hertz': ['#ffd100', '#000000'],  # Yellow, black
    'Enterprise': ['#006747', '#ffffff'],  # Green
    'Avis': ['#d4002a', '#ffffff'],  # Red
    'Budget': ['#ff6600', '#ffffff'],  # Orange

    # Real Estate
    'CBRE': ['#003f2d', '#ffffff'],  # Green
    'JLL': ['#e30613', '#000000'],  # Red, black
    'Jones_Lang_LaSalle': ['#e30613', '#000000'],  # Red, black
    'Cushman_Wakefield': ['#c8102e', '#000000'],  # Red, black
    'Colliers': ['#00457c', '#ffffff'],  # Blue
    'Newmark': ['#002855', '#ffffff'],  # Navy
    'Marcus_Millichap': ['#0033a0', '#ffffff'],  # Blue
    'Eastdil_Secured': ['#1c3f6e', '#ffffff'],  # Navy
    'Brookfield': ['#003c71', '#ffffff'],  # Navy
    'Blackstone': ['#000000', '#ffffff'],  # Black
    'BlackRock': ['#000000', '#ffffff'],  # Black
    'Starwood': ['#003366', '#ffffff'],  # Navy
    'Prologis': ['#0046ad', '#ffffff'],  # Blue
    'Simon_Property': ['#003087', '#ffffff'],  # Blue
    'Vornado': ['#003c71', '#ffffff'],  # Navy
    'Boston_Properties': ['#003c71', '#ffffff'],  # Navy
    'SL_Green': ['#005732', '#ffffff'],  # Green
    'Equity_Residential': ['#003f87', '#ffffff'],  # Blue
    'AvalonBay': ['#003087', '#ffffff'],  # Blue
    'Essex_Property': ['#003c71', '#ffffff'],  # Navy
    'Camden': ['#003c71', '#ffffff'],  # Navy
    'UDR': ['#001f5b', '#ffffff'],  # Navy
    'Mid_America': ['#003c71', '#ffffff'],  # Navy
    'Invitation_Homes': ['#003c71', '#ffffff'],  # Navy
    'American_Homes': ['#003087', '#ffffff'],  # Blue
    'Greystar': ['#003c71', '#ffffff'],  # Navy
    'Lincoln_Property': ['#003c71', '#ffffff'],  # Navy
    'Hines': ['#003c71', '#ffffff'],  # Navy
    'Tishman_Speyer': ['#003c71', '#ffffff'],  # Navy
    'Related_Companies': ['#003c71', '#ffffff'],  # Navy
    'Silverstein': ['#003c71', '#ffffff'],  # Navy
    'RXR': ['#003c71', '#ffffff'],  # Navy

    # Insurance
    'State_Farm': ['#b81d24', '#ffffff'],  # Red
    'Allstate': ['#0033a1', '#ff6600'],  # Blue, orange
    'Geico': ['#0b6ab2', '#ffffff'],  # Blue
    'Progressive': ['#0077c8', '#ffffff'],  # Blue
    'Liberty_Mutual': ['#003a70', '#f2d53c'],  # Navy, gold
    'Nationwide': ['#003b5c', '#ffffff'],  # Navy
    'Travelers': ['#e4002b', '#ffffff'],  # Red
    'MetLife': ['#00ae4d', '#ffffff'],  # Green
    'Prudential': ['#003c71', '#f58025'],  # Navy, orange
    'AIG': ['#0072ce', '#ffffff'],  # Blue
    'Aflac': ['#00a3e0', '#ffffff'],  # Blue

    # Sports apparel
    'Nike': ['#000000', '#f5721b'],  # Black, orange
    'Adidas': ['#000000'],  # Black
    'Under_Armour': ['#1d1d1d', '#ffffff'],  # Black
    'Puma': ['#000000', '#ff0000'],  # Black, red
    'Reebok': ['#000000', '#ff0000'],  # Black, red
    'New_Balance': ['#cf0a2c', '#000000'],  # Red, black
    'ASICS': ['#001489', '#ffffff'],  # Blue

    # Entertainment
    'Disney': ['#113ccf', '#000000'],  # Blue, black
    'Warner_Bros': ['#004a98', '#000000'],  # Blue, black
    'Universal': ['#000000', '#ffffff'],  # Black
    'Paramount': ['#0066cc', '#ffffff'],  # Blue
    'Sony_Pictures': ['#000000'],  # Black
    'MGM': ['#b59a58', '#000000'],  # Gold, black
    'Lionsgate': ['#f6a800', '#000000'],  # Gold, black
    'AMC': ['#c8102e', '#000000'],  # Red, black
    'AMC_Entertainment': ['#c8102e', '#000000'],  # Red, black
    'AMC_Entertainment_Holdings_Inc_AMC': ['#c8102e', '#000000'],  # Red, black
    'Regal': ['#8b0000', '#ffffff'],  # Dark red
    'Cinemark': ['#a7001e', '#ffffff'],  # Red

    # Telecom
    'AT_T': ['#00a8e0', '#ffffff'],  # Blue
    'Verizon': ['#cd040b', '#ffffff'],  # Red
    'T_Mobile': ['#e20074', '#ffffff'],  # Magenta
    'Sprint': ['#fee100', '#000000'],  # Yellow, black
    'Comcast': ['#ff0000', '#000000'],  # Red, black
    'Xfinity': ['#000000', '#ffffff'],  # Black
    'Charter': ['#0077c8', '#ffffff'],  # Blue
    'Spectrum': ['#0066c3', '#ffffff'],  # Blue
    'Cox': ['#fd6400', '#ffffff'],  # Orange
    'CenturyLink': ['#3ab54a', '#00aeef'],  # Green, blue
    'Lumen': ['#3ab54a', '#00aeef'],  # Green, blue

    # Education
    'Harvard': ['#a51c30', '#1e1e1e'],  # Crimson, black
    'Yale': ['#00356b', '#ffffff'],  # Blue
    'Princeton': ['#ff6f00', '#000000'],  # Orange, black
    'Stanford': ['#8c1515', '#ffffff'],  # Cardinal
    'MIT': ['#a31f34', '#8a8b8c'],  # Red, gray
    'Columbia': ['#b9d9eb', '#002b7f'],  # Light blue, blue
    'Penn': ['#011f5b', '#990000'],  # Blue, red
    'Cornell': ['#b31b1b', '#ffffff'],  # Red
    'Brown': ['#4e3629', '#ffffff'],  # Brown
    'Dartmouth': ['#00693e', '#ffffff'],  # Green
    'Duke': ['#003087', '#ffffff'],  # Blue
    'Northwestern': ['#4e2a84', '#ffffff'],  # Purple
    'Chicago': ['#800000', '#ffffff'],  # Maroon
    'USC': ['#990000', '#ffc72c'],  # Cardinal, gold
    'UCLA': ['#2774ae', '#ffd100'],  # Blue, gold
    'Berkeley': ['#003262', '#fdb515'],  # Blue, gold
    'NYU': ['#57068c', '#ffffff'],  # Purple
    'Boston_University': ['#cc0000', '#ffffff'],  # Red
    'Georgetown': ['#041e42', '#63666a'],  # Navy, gray
    'Boston_College': ['#8b2131', '#bc9b6a'],  # Maroon, gold
    'American_University': ['#002147', '#c41230'],  # Navy, red

    # Energy
    'Exxon': ['#ed1c24', '#ffffff'],  # Red
    'ExxonMobil': ['#ed1c24', '#ffffff'],  # Red
    'Chevron': ['#0066b2', '#d9272e'],  # Blue, red
    'Shell': ['#fbce07', '#dd1d21'],  # Yellow, red
    'BP': ['#009a54', '#fff200'],  # Green, yellow
    'ConocoPhillips': ['#ed1c24', '#ffffff'],  # Red
    'Phillips_66': ['#c8102e', '#ffffff'],  # Red
    'Valero': ['#002f87', '#ffffff'],  # Blue
    'Marathon': ['#d3242b', '#ffffff'],  # Red
    'Duke_Energy': ['#00b5e2', '#ffffff'],  # Blue
    'Southern_Company': ['#00263a', '#ffffff'],  # Navy
    'Dominion': ['#002663', '#ffffff'],  # Navy
    'Exelon': ['#0057a0', '#ffffff'],  # Blue
    'NextEra': ['#003366', '#ffffff'],  # Navy
    'PGE': ['#004990', '#ffffff'],  # Blue
    'Pacific_Gas_Electric': ['#004990', '#ffffff'],  # Blue
    'Edison': ['#001f5b', '#ffffff'],  # Navy
    'Southern_California_Edison': ['#001f5b', '#ffffff'],  # Navy
    'Sempra': ['#003768', '#ffffff'],  # Navy
    'SDG_E': ['#003768', '#ffffff'],  # Navy
    'ConEdison': ['#002f6c', '#ff6e00'],  # Navy, orange

    # More well-known brands
    'Starbucks': ['#00704a', '#1e3932'],  # Green
    'Nike': ['#000000'],  # Black
    'Coca_Cola': ['#f40009', '#ffffff'],  # Red
    'Pepsi': ['#004883', '#c9002b', '#ffffff'],  # Blue, red
    'FedEx': ['#4d148c', '#ff6600'],  # Purple, orange
    'UPS': ['#351c15', '#ffb500'],  # Brown, gold
    'DHL': ['#ffcc00', '#d40511'],  # Yellow, red
    'USPS': ['#004b87', '#cc0000'],  # Blue, red
    '7_Eleven': ['#0cae4c', '#ff0000', '#ff6600'],  # Green, red, orange
    'Lowes': ['#004990', '#ffffff'],  # Blue
    'Home_Depot': ['#f96302', '#ffffff'],  # Orange
    'Best_Buy': ['#0046be', '#fff200'],  # Blue, yellow
    'GameStop': ['#000000', '#ff0000'],  # Black, red
    'Apple_Inc': ['#000000', '#a3aaae'],  # Black, silver
    'Spotify': ['#1ed760', '#000000'],  # Green, black
    'Twitter': ['#1da1f2', '#000000'],  # Blue, black
    'X': ['#000000', '#ffffff'],  # Black
    'LinkedIn': ['#0077b5', '#ffffff'],  # Blue
    'Instagram': ['#e4405f', '#833ab4', '#fcaf45'],  # Pink, purple, orange
    'TikTok': ['#000000', '#ff0050', '#00f2ea'],  # Black, red, teal
    'Snapchat': ['#fffc00', '#000000'],  # Yellow, black
    'Pinterest': ['#bd081c', '#ffffff'],  # Red
    'Reddit': ['#ff4500', '#000000'],  # Orange, black
    'Discord': ['#5865f2', '#ffffff'],  # Purple, white
    'Slack': ['#4a154b', '#36c5f0', '#2eb67d', '#ecb22e', '#e01e5a'],  # Purple, blue, green, yellow, red
    'Zoom': ['#2d8cff', '#ffffff'],  # Blue
    'Dropbox': ['#0061ff', '#ffffff'],  # Blue
    'Box': ['#0061d5', '#ffffff'],  # Blue
    'Airbnb': ['#ff5a5f', '#ffffff'],  # Red/pink
    'Uber': ['#000000', '#ffffff'],  # Black
    'Lyft': ['#ff00bf', '#ffffff'],  # Pink/magenta
    'DoorDash': ['#ff3008', '#ffffff'],  # Red
    'Grubhub': ['#f63440', '#ffffff'],  # Red
    'Instacart': ['#43b02a', '#ffffff'],  # Green
    'Shopify': ['#96bf48', '#ffffff'],  # Green
    'Etsy': ['#f45800', '#ffffff'],  # Orange
    'eBay': ['#e53238', '#0064d2', '#f5af02', '#86b817'],  # Red, blue, yellow, green
    'Craigslist': ['#5d0098', '#ffffff'],  # Purple
    'Zillow': ['#006aff', '#ffffff'],  # Blue
    'Redfin': ['#a02021', '#ffffff'],  # Red
    'Realtor': ['#d92228', '#ffffff'],  # Red
    'Trulia': ['#469a3c', '#ffffff'],  # Green
}

def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(rgb):
    """Convert RGB tuple to hex string."""
    return '#{:02x}{:02x}{:02x}'.format(int(rgb[0]), int(rgb[1]), int(rgb[2]))

def color_distance(c1, c2):
    """Calculate Euclidean distance between two RGB colors."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))

def get_dominant_colors(image_path, num_colors=5):
    """Extract dominant colors from an image, ignoring transparency."""
    try:
        img = Image.open(image_path).convert('RGBA')
        pixels = list(img.getdata())

        # Filter out transparent/near-transparent pixels and white/near-white
        visible_pixels = []
        for p in pixels:
            if len(p) == 4:
                r, g, b, a = p
            else:
                r, g, b = p
                a = 255

            # Skip transparent pixels
            if a < 128:
                continue

            # Skip near-white pixels (background)
            if r > 240 and g > 240 and b > 240:
                continue

            # Skip near-black pixels if they're clearly background
            # (but keep if significant)

            visible_pixels.append((r, g, b))

        if not visible_pixels:
            return []

        # Quantize colors for better grouping
        quantized = []
        for r, g, b in visible_pixels:
            # Round to nearest 16 for grouping
            qr = (r // 16) * 16
            qg = (g // 16) * 16
            qb = (b // 16) * 16
            quantized.append((qr, qg, qb))

        # Count occurrences
        counter = Counter(quantized)

        # Get top colors
        top_colors = counter.most_common(num_colors)

        return [(rgb_to_hex(c), count) for c, count in top_colors]

    except Exception as e:
        print(f"Error processing {image_path}: {e}")
        return []

def normalize_brand_name(filename):
    """Convert filename to brand name format for matching."""
    # Remove .png extension
    name = filename.replace('.png', '')
    return name

def find_brand_match(logo_name):
    """Find matching brand in our database."""
    # Direct match
    if logo_name in BRAND_COLORS:
        return logo_name

    # Try common variations
    variations = [
        logo_name.replace('_', ' '),
        logo_name.replace(' ', '_'),
        logo_name.title(),
        logo_name.upper(),
        logo_name.lower(),
    ]

    for var in variations:
        if var in BRAND_COLORS:
            return var

    # Partial match - if brand name contains the logo name or vice versa
    for brand in BRAND_COLORS.keys():
        brand_lower = brand.lower().replace('_', '')
        logo_lower = logo_name.lower().replace('_', '')

        if brand_lower == logo_lower:
            return brand
        if brand_lower in logo_lower or logo_lower in brand_lower:
            # Only if significant overlap
            if len(brand_lower) > 3 and len(logo_lower) > 3:
                return brand

    return None

def check_color_match(logo_colors, expected_colors, threshold=80):
    """
    Check if logo colors match expected brand colors.
    Returns (is_match, explanation)
    """
    if not logo_colors or not expected_colors:
        return True, "No colors to compare"

    expected_rgb = [hex_to_rgb(c) for c in expected_colors]

    # Get significant logo colors (more than 5% of non-transparent pixels)
    total_pixels = sum(count for _, count in logo_colors)
    significant_colors = [(hex_to_rgb(c.lstrip('#')), count) for c, count in logo_colors
                         if count > total_pixels * 0.05]

    if not significant_colors:
        significant_colors = [(hex_to_rgb(logo_colors[0][0].lstrip('#')), logo_colors[0][1])]

    # Check if any significant logo color is close to any expected color
    matches_found = []
    mismatches = []

    for logo_rgb, count in significant_colors:
        best_match = None
        best_distance = float('inf')

        for exp_rgb in expected_rgb:
            dist = color_distance(logo_rgb, exp_rgb)
            if dist < best_distance:
                best_distance = dist
                best_match = exp_rgb

        if best_distance < threshold:
            matches_found.append((logo_rgb, best_match, best_distance))
        else:
            mismatches.append((logo_rgb, best_distance, count))

    # If we have significant mismatches (colors that don't match any expected)
    if mismatches:
        # Check if mismatched colors are dominant
        mismatch_pixels = sum(count for _, _, count in mismatches)
        if mismatch_pixels > total_pixels * 0.3:  # More than 30% of pixels are wrong color
            mismatch_hex = [rgb_to_hex(rgb) for rgb, _, _ in mismatches]
            expected_hex = expected_colors[:3]
            return False, f"Wrong colors: found {mismatch_hex}, expected {expected_hex}"

    return True, "Colors match"

def main():
    print("=" * 70)
    print("LOGO COLOR CHECKER")
    print("=" * 70)
    print(f"\nScanning logos in: {LOGOS_DIR}")
    print(f"Known brands in database: {len(BRAND_COLORS)}")
    print()

    # Get all logo files
    logo_files = [f for f in os.listdir(LOGOS_DIR) if f.endswith('.png')]
    print(f"Total logos found: {len(logo_files)}")

    # Track results
    problems = []
    checked = 0
    matched_brands = 0

    for logo_file in sorted(logo_files):
        logo_path = os.path.join(LOGOS_DIR, logo_file)
        brand_name = normalize_brand_name(logo_file)

        # Try to find matching brand
        matched_brand = find_brand_match(brand_name)

        if matched_brand:
            matched_brands += 1
            expected_colors = BRAND_COLORS[matched_brand]

            # Get logo colors
            logo_colors = get_dominant_colors(logo_path)

            if logo_colors:
                is_match, explanation = check_color_match(logo_colors, expected_colors)
                checked += 1

                if not is_match:
                    problems.append({
                        'file': logo_file,
                        'brand': matched_brand,
                        'expected': expected_colors,
                        'found': [c for c, _ in logo_colors[:3]],
                        'issue': explanation
                    })
                    print(f"❌ {logo_file}")
                    print(f"   Brand: {matched_brand}")
                    print(f"   Expected: {expected_colors[:3]}")
                    print(f"   Found: {[c for c, _ in logo_colors[:3]]}")
                    print(f"   Issue: {explanation}")
                    print()

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total logos: {len(logo_files)}")
    print(f"Matched to known brands: {matched_brands}")
    print(f"Checked for color issues: {checked}")
    print(f"Problems found: {len(problems)}")

    if problems:
        print("\n" + "=" * 70)
        print("PROBLEMATIC LOGOS")
        print("=" * 70)
        for p in problems:
            print(f"\n{p['file']}")
            print(f"  Brand: {p['brand']}")
            print(f"  Expected colors: {p['expected'][:3]}")
            print(f"  Actual colors: {p['found']}")
            print(f"  Issue: {p['issue']}")

    return problems

if __name__ == "__main__":
    main()
