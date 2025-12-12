#!/usr/bin/env python3
"""
Add comprehensive search aliases to portfolio_organizations.csv
This makes search REALLY GOOD so CAL, USC, U of C, MIT, NYC, etc. all work!
"""

import pandas as pd
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import PORTFOLIO_ORGS_PATH

# =============================================================================
# COMPREHENSIVE MANUAL ALIASES - THE BIG LIST!
# =============================================================================

MANUAL_ALIASES = {
    # =========================================================================
    # UNIVERSITIES - ALL THE WAYS PEOPLE SEARCH
    # =========================================================================

    # UC System - CRITICAL for "CAL" searches
    "University of California": "UC|Cal|U of C|UofC|UC System|California|Berkeley|Cal Berkeley|UCB|UCLA|UCSF|UCSD|UCI|UCR|UCSC|UCD|UC Davis|UC Irvine|UC Riverside|UC Santa Cruz|UC San Diego|UC Santa Barbara|UCSB|UC Merced|Golden Bears|Bruins",
    "California State University": "CSU|Cal State|CSUN|CSUF|CSULA|CSULB|CSUDH|CSUEB|Cal State Fullerton|Cal State Northridge|Cal State LA|Cal State Long Beach|Cal State Dominguez|Cal State East Bay|San Jose State|SJSU|Fresno State|Sacramento State|San Diego State|SDSU|Cal Poly|Pomona|Humboldt",

    # USC - Major one
    "University Of Southern California": "USC|SoCal|Southern Cal|Southern California|Trojans|U of SC|So Cal",

    # Ivy League & Elite Schools
    "Harvard University": "Harvard|Crimson|HU|Cambridge",
    "Stanford University": "Stanford|The Farm|Cardinal|Leland Stanford|SU",
    "Massachusetts Institute Of Technology": "MIT|Mass Tech|Massachusetts Tech|Tech",
    "Columbia University": "Columbia|Lions|CU|Morningside",
    "Cornell University": "Cornell|Big Red|Ithaca",
    "University Of Pennsylvania": "UPenn|Penn|U of P|Pennsylvania|Quakers|Wharton",
    "Yale University": "Yale|Bulldogs|Eli|New Haven",
    "Princeton University": "Princeton|Tigers|Nassau",
    "Brown University": "Brown|Bears|Providence",
    "Dartmouth College": "Dartmouth|Big Green|Hanover",

    # Major Research Universities
    "University Of Chicago": "UChicago|U of C|U Chicago|Chicago|Maroons",
    "Northwestern University": "Northwestern|NU|Wildcats|Evanston",
    "Duke University": "Duke|Blue Devils|Durham",
    "Johns Hopkins University": "JHU|Hopkins|Johns Hopkins|Blue Jays|Baltimore",
    "University of Washington (UW)": "UW|U Dub|Huskies|Washington|Seattle|UDub",
    "University Of Michigan": "UMich|Michigan|U of M|Wolverines|Ann Arbor|UM",
    "University Of Texas": "UT|Texas|Longhorns|Austin|UT Austin|Hook Em",
    "University Of Florida": "UF|Florida|Gators|Gainesville",
    "Ohio State University": "OSU|Ohio State|Buckeyes|Columbus|tOSU",
    "Penn State University": "Penn State|PSU|Nittany Lions|State College",
    "University Of Wisconsin": "UW|Wisconsin|Badgers|Madison|UW Madison",
    "University Of Minnesota": "UMN|Minnesota|Gophers|Twin Cities|U of M",
    "University Of Illinois": "UIUC|Illinois|Illini|Urbana|Champaign|U of I",
    "Purdue University": "Purdue|Boilermakers|West Lafayette",
    "Indiana University": "IU|Indiana|Hoosiers|Bloomington",
    "University Of Iowa": "Iowa|Hawkeyes|Iowa City",
    "University Of Colorado": "CU|Colorado|Buffaloes|Boulder|CU Boulder",
    "University Of Arizona": "UA|Arizona|Wildcats|Tucson|U of A",
    "Arizona State University": "ASU|Arizona State|Sun Devils|Tempe",
    "University Of Oregon": "UO|Oregon|Ducks|Eugene",
    "Oregon State University": "OSU|Oregon State|Beavers|Corvallis",
    "University Of Utah": "Utah|Utes|Salt Lake",

    # NYC Universities
    "New York University (NYU)": "NYU|New York U|Violet|Violets|Washington Square|Greenwich Village",
    "City University of New York (CUNY)": "CUNY|City University|City College|CCNY|Hunter|Baruch|Brooklyn College|Queens College|Lehman|John Jay",
    "Fordham University": "Fordham|Rams|Bronx|Rose Hill",
    "The New School": "New School|Parsons|Eugene Lang",

    # Boston Area
    "Boston University": "BU|Boston U|Terriers|Commonwealth Ave",
    "Boston College": "BC|Eagles|Chestnut Hill",
    "Northeastern University": "Northeastern|NEU|Huskies|Huntington",
    "Tufts University": "Tufts|Jumbos|Medford",
    "Brandeis University": "Brandeis|Judges|Waltham",
    "Suffolk University": "Suffolk|Rams|Downtown Boston",
    "Emerson College": "Emerson|Lions|Theater District",
    "Berklee College Of Music": "Berklee|Berklee Music|Back Bay",

    # DC Area
    "George Washington University": "GWU|GW|George Washington|Colonials|Foggy Bottom",
    "Georgetown University": "Georgetown|Hoyas|GU|Hilltop",
    "American University": "AU|American|Eagles|Tenleytown",
    "Howard University": "Howard|Bison|HU|HBCU",
    "Catholic University Of America": "CUA|Catholic|Cardinals",
    "Gallaudet University": "Gallaudet|Bison",

    # Chicago Area
    "DePaul University": "DePaul|Blue Demons|Lincoln Park",
    "Loyola University Chicago": "Loyola|Ramblers|Rogers Park|LUC",
    "Illinois Institute Of Technology": "IIT|Illinois Tech|Scarlet Hawks",
    "University Of Illinois Chicago": "UIC|Flames|Chicago",

    # West Coast
    "University Of San Francisco": "USF|SF|Dons|Hilltop",
    "Santa Clara University": "SCU|Santa Clara|Broncos",
    "University Of San Diego": "USD|San Diego|Toreros",
    "Pepperdine University": "Pepperdine|Waves|Malibu",
    "Loyola Marymount University": "LMU|Loyola Marymount|Lions",
    "Chapman University": "Chapman|Panthers|Orange",
    "University Of Portland": "UP|Portland|Pilots",
    "Portland State University": "PSU|Portland State|Vikings",
    "Seattle University": "SU|Seattle|Redhawks",
    "Gonzaga University": "Gonzaga|Zags|Bulldogs|Spokane",

    # St. Louis
    "Washington University in St. Louis": "WashU|Wash U|WUSTL|St Louis|Bears|Danforth",
    "Saint Louis University": "SLU|St Louis|Billikens",

    # Other Major Schools
    "University Of Denver": "DU|Denver|Pioneers|Denver U",
    "University Of Miami": "UM|Miami|Hurricanes|Canes|The U",
    "University Of Pittsburgh": "Pitt|Pittsburgh|Panthers",
    "Carnegie Mellon University": "CMU|Carnegie Mellon|Tartans|Pittsburgh",
    "Emory University": "Emory|Eagles|Atlanta|Druid Hills",
    "Vanderbilt University": "Vandy|Vanderbilt|Commodores|Nashville",
    "Rice University": "Rice|Owls|Houston",
    "Tulane University": "Tulane|Green Wave|New Orleans|NOLA",
    "Wake Forest University": "Wake|Wake Forest|Demon Deacons|Winston Salem",
    "University Of Notre Dame": "Notre Dame|ND|Irish|Fighting Irish|South Bend",
    "University Of Virginia": "UVA|Virginia|Cavaliers|Wahoos|Charlottesville",
    "Virginia Tech": "VT|Virginia Tech|Hokies|Blacksburg",
    "University Of Maryland": "UMD|Maryland|Terrapins|Terps|College Park",
    "Rutgers University": "Rutgers|Scarlet Knights|New Brunswick",
    "Temple University": "Temple|Owls|North Philly",
    "Drexel University": "Drexel|Dragons|University City",
    "University Of Connecticut": "UConn|Connecticut|Huskies|Storrs",
    "University Of Massachusetts": "UMass|Massachusetts|Minutemen|Amherst",
    "University Of Rhode Island": "URI|Rhode Island|Rams|Kingston",
    "University Of Vermont": "UVM|Vermont|Catamounts|Burlington",
    "University Of New Hampshire": "UNH|New Hampshire|Wildcats|Durham",
    "University Of Maine": "UMaine|Maine|Black Bears|Orono",

    # California Private Schools
    "Loma Linda University": "Loma Linda|LLU|Adventist",
    "Azusa Pacific University": "APU|Azusa Pacific|Cougars",
    "Biola University": "Biola|Eagles|La Mirada",
    "Academy Of Art University": "AAU|Academy of Art|SF Art School",

    # =========================================================================
    # CITIES - ALL ABBREVIATIONS AND NICKNAMES
    # =========================================================================

    "City Of New York": "NYC|New York|NY|NY City|Big Apple|Manhattan|Gotham|New York City|The City",
    "City Of Los Angeles": "LA|Los Angeles|L.A.|LA City|City of Angels|SoCal|Southern California",
    "City Of Chicago": "Chicago|Chi|Chi-Town|Windy City|CHI|Second City",
    "City Of Philadelphia": "Philly|Philadelphia|PHL|Phila|City of Brotherly Love",
    "City Of Houston": "Houston|HTX|H-Town|Space City",
    "City Of Phoenix": "Phoenix|PHX|Valley of the Sun",
    "City Of San Antonio": "San Antonio|SA|Alamo City|SATX",
    "City Of San Diego": "San Diego|SD|America's Finest City",
    "City Of Dallas": "Dallas|DFW|Big D",
    "City Of San Jose": "San Jose|SJ|Silicon Valley",
    "City Of Austin": "Austin|ATX|Keep Austin Weird",
    "City Of Jacksonville": "Jacksonville|Jax|JAX|Duval",
    "City Of Fort Worth": "Fort Worth|FTW|Cowtown",
    "City Of Columbus": "Columbus|Cbus|614",
    "City Of Charlotte": "Charlotte|CLT|Queen City",
    "City Of San Francisco": "SF|San Francisco|Frisco|The City|Bay Area|San Fran",
    "City Of Indianapolis": "Indianapolis|Indy|Circle City|Naptown",
    "City Of Seattle": "Seattle|SEA|Emerald City|Pacific Northwest|PNW",
    "City Of Denver": "Denver|DEN|Mile High|Mile High City|5280",
    "City Of Boston": "Boston|BOS|Beantown|The Hub|Bean",
    "City Of Detroit": "Detroit|DTW|Motor City|Motown|D",
    "City Of Nashville": "Nashville|Music City|NashVegas",
    "City Of Portland": "Portland|PDX|Rose City|Stumptown|Rip City",
    "City Of Memphis": "Memphis|MEM|Bluff City",
    "City Of Oklahoma City": "OKC|Oklahoma City|OK City",
    "City Of Las Vegas": "Vegas|Las Vegas|LV|Sin City",
    "City Of Louisville": "Louisville|Lou|Derby City|502",
    "City Of Baltimore": "Baltimore|B-More|Charm City|BWI",
    "City Of Milwaukee": "Milwaukee|MKE|Brew City|Cream City",
    "City Of Albuquerque": "Albuquerque|ABQ|Duke City",
    "City Of Tucson": "Tucson|TUS|Old Pueblo",
    "City Of Fresno": "Fresno|FAT|Raisin Capital",
    "City Of Sacramento": "Sacramento|Sac|SAC|Sactown|Capital City",
    "City Of Atlanta": "Atlanta|ATL|Hotlanta|The A|A-Town",
    "City Of Kansas City": "KC|Kansas City|KCMO|City of Fountains",
    "City Of Miami": "Miami|MIA|Magic City|305",
    "City Of Oakland": "Oakland|OAK|The Town|East Bay",
    "City Of Minneapolis": "Minneapolis|MPLS|Twin Cities|Mill City",
    "City Of Cleveland": "Cleveland|CLE|The Land|Forest City",
    "City Of New Orleans": "New Orleans|NOLA|Big Easy|Crescent City|504",
    "City Of Tampa": "Tampa|TPA|Cigar City|Tampa Bay",
    "City Of Pittsburgh": "Pittsburgh|PGH|Steel City|412|Burgh",
    "City Of St. Louis": "St. Louis|STL|Gateway City|314|The Lou",
    "City Of Cincinnati": "Cincinnati|Cincy|Queen City|Nati|513",
    "City Of Cambridge": "Cambridge|CAM|Harvard Square",
    "City Of Berkeley": "Berkeley|Cal|East Bay",
    "City Of Pasadena": "Pasadena|PAS|Crown City|Rose City",
    "City Of Long Beach": "Long Beach|LB|LBC|562",
    "City Of Santa Monica": "Santa Monica|SM|Bay City",
    "City Of Burbank": "Burbank|Media Capital",
    "City Of Glendale": "Glendale|GDL",
    "City Of Anaheim": "Anaheim|OC|Orange County",
    "City Of Irvine": "Irvine|OC|Orange County",

    # =========================================================================
    # STATES & DISTRICTS
    # =========================================================================

    "State Of New York": "NY|New York State|New York|NYS|Empire State",
    "State of California": "CA|California|Cali|Golden State|West Coast",
    "State Of Texas": "TX|Texas|Lone Star State",
    "State Of Florida": "FL|Florida|Sunshine State",
    "State Of Illinois": "IL|Illinois|Prairie State",
    "State Of Pennsylvania": "PA|Pennsylvania|Keystone State",
    "State Of Ohio": "OH|Ohio|Buckeye State",
    "State Of Georgia": "GA|Georgia|Peach State",
    "State Of North Carolina": "NC|North Carolina|Tar Heel State",
    "State Of Michigan": "MI|Michigan|Great Lakes State",
    "State Of New Jersey": "NJ|New Jersey|Garden State",
    "State Of Virginia": "VA|Virginia|Old Dominion",
    "State Of Washington": "WA|Washington|Washington State|Evergreen State",
    "State Of Arizona": "AZ|Arizona|Grand Canyon State",
    "State Of Massachusetts": "MA|Mass|Massachusetts|Bay State",
    "State Of Tennessee": "TN|Tennessee|Volunteer State",
    "State Of Indiana": "IN|Indiana|Hoosier State",
    "State Of Maryland": "MD|Maryland|Old Line State",
    "State Of Wisconsin": "WI|Wisconsin|Badger State",
    "State Of Colorado": "CO|Colorado|Centennial State",
    "State Of Minnesota": "MN|Minnesota|North Star State",
    "State Of Oregon": "OR|Oregon|Beaver State",
    "State Of Connecticut": "CT|Connecticut|Constitution State",
    "State Of Utah": "UT|Utah|Beehive State",
    "State Of Nevada": "NV|Nevada|Silver State",
    "State Of Kentucky": "KY|Kentucky|Bluegrass State",
    "State Of Missouri": "MO|Missouri|Show Me State",
    "State Of Oklahoma": "OK|Oklahoma|Sooner State",
    "State Of Louisiana": "LA|Louisiana|Pelican State|NOLA",
    "State Of Iowa": "IA|Iowa|Hawkeye State",
    "State Of Kansas": "KS|Kansas|Sunflower State",

    "District Of Columbia": "DC|Washington DC|Washington|DMV|District|Capitol|The District|Federal|WDC",
    "Commonwealth Of Massachusetts": "MA|Mass|Massachusetts|Bay State|Boston|Cambridge",
    "Commonwealth Of Virginia": "VA|Virginia|Old Dominion|NoVA|NOVA",
    "Commonwealth Of Pennsylvania": "PA|Penn|Pennsylvania|Keystone",

    # =========================================================================
    # COUNTIES
    # =========================================================================

    "Los Angeles County": "LA County|Los Angeles|LAC",
    "Cook County": "Cook|Chicago|Chicagoland",
    "Harris County": "Harris|Houston",
    "Maricopa County": "Maricopa|Phoenix",
    "San Diego County": "San Diego County|SD County",
    "Orange County": "OC|Orange|Orange County|Irvine|Newport",
    "Riverside County": "Riverside|IE|Inland Empire",
    "San Bernardino County": "San Bernardino|IE|Inland Empire|SB County",
    "King County": "King|Seattle|Puget Sound",
    "Santa Clara County": "Santa Clara|Silicon Valley|South Bay",
    "Alameda County": "Alameda|East Bay|Oakland",
    "Philadelphia County": "Philly|Philadelphia|PHL",

    # =========================================================================
    # FEDERAL AGENCIES
    # =========================================================================

    "General Services Administration (GSA)": "GSA|General Services|Federal|Fed|Government",
    "Department Of Homeland Security": "DHS|Homeland Security|Homeland|Federal",
    "Department Of Defense": "DOD|DoD|Defense|Pentagon|Military",
    "Department Of Veterans Affairs": "VA|Veterans|Veterans Affairs|DVA",
    "Department Of Justice": "DOJ|Justice|Federal",
    "Department Of State": "DOS|State Department|State Dept|Foggy Bottom",
    "Department Of Energy": "DOE|Energy|Federal",
    "Department Of Transportation": "DOT|Transportation|Federal",
    "Department Of Education": "ED|Education|Federal",
    "Department Of Health And Human Services": "HHS|Health|Human Services|Federal",
    "Department Of Agriculture": "USDA|Agriculture|Ag",
    "Department Of Commerce": "DOC|Commerce|Federal",
    "Department Of Labor": "DOL|Labor|Federal",
    "Department Of The Interior": "DOI|Interior|Federal",
    "Department Of Treasury": "Treasury|Federal",
    "Environmental Protection Agency": "EPA|Environment|Environmental",
    "Social Security Administration": "SSA|Social Security",
    "Federal Bureau Of Investigation": "FBI|Federal Bureau|Bureau",
    "Internal Revenue Service": "IRS|Tax|Revenue",
    "Central Intelligence Agency": "CIA|Intelligence|Langley",
    "National Aeronautics And Space Administration": "NASA|Space|Aeronautics",
    "Federal Aviation Administration": "FAA|Aviation|Air",
    "Federal Emergency Management Agency": "FEMA|Emergency|Disaster",
    "Securities And Exchange Commission": "SEC|Securities|Exchange",
    "Federal Communications Commission": "FCC|Communications|Telecom",
    "Federal Trade Commission": "FTC|Trade|Consumer",
    "Consumer Financial Protection Bureau": "CFPB|Consumer|Financial",
    "Small Business Administration": "SBA|Small Business",
    "Centers For Disease Control": "CDC|Disease Control|Atlanta",
    "National Institutes Of Health": "NIH|Health|Bethesda",
    "National Science Foundation": "NSF|Science|Research",
    "US Postal Service": "USPS|Post Office|Mail|Postal",

    # =========================================================================
    # POLICE & FIRE DEPARTMENTS
    # =========================================================================

    "New York City Police Department (NYPD)": "NYPD|New York Police|NYC Police|NY Police|NY Cops",
    "Los Angeles Police Department (LAPD)": "LAPD|LA Police|Los Angeles Police|LA Cops",
    "Chicago Police Department": "CPD|Chicago Police|Chi Police",
    "Metropolitan Police Department Of The District Of Columbia (MPD)": "MPD|DC Police|Metro Police|Washington Police",
    "Boston Police Department": "BPD|Boston Police",
    "Philadelphia Police Department": "PPD|Philly Police|Philadelphia Police",
    "Houston Police Department": "HPD|Houston Police",
    "Phoenix Police Department": "PHX Police|Phoenix Police",
    "Dallas Police Department": "DPD|Dallas Police",
    "San Francisco Police Department": "SFPD|SF Police|San Francisco Police",
    "Seattle Police Department": "SPD|Seattle Police",
    "Denver Police Department": "DPD|Denver Police",
    "Miami Police Department": "MPD|Miami Police",
    "Atlanta Police Department": "APD|Atlanta Police",

    "New York City Fire Department": "FDNY|NYC Fire|New York Fire|NY Fire",
    "Los Angeles Fire Department": "LAFD|LA Fire|Los Angeles Fire",
    "Chicago Fire Department": "CFD|Chicago Fire",
    "Dc Fire And Emergency Medical Services Department (DCFEMS)": "DCFEMS|DC Fire|DC EMS|Washington Fire",

    # =========================================================================
    # REAL ESTATE COMPANIES
    # =========================================================================

    "CBRE Group (CBRE)": "CBRE|CB Richard Ellis|Commercial Real Estate",
    "Jones Lang LaSalle (JLL)": "JLL|Jones Lang|JL LaSalle|Jones LaSalle",
    "Cushman & Wakefield": "C&W|Cushman|CW|Cushman Wakefield",
    "Newmark": "Newmark|NMK|Newmark Knight Frank|NKF",
    "Colliers": "Colliers|Colliers International",
    "Avison Young": "AY|Avison|Avison Young",
    "Marcus & Millichap": "M&M|Marcus Millichap|Marcus",
    "Transwestern": "TW|Transwestern",
    "NAI Global": "NAI|NAI Global",

    # Major REITs & Owners
    "Boston Properties (BXP)": "BXP|Boston Properties|BP",
    "Brookfield": "Brookfield|BPY|Brookfield Properties",
    "Blackstone": "BX|Blackstone|Black Stone",
    "Vornado Realty Trust": "VNO|Vornado|Vornado Realty",
    "SL Green": "SLG|SL Green|Green Realty",
    "Kilroy Realty": "KRC|Kilroy|Kilroy Realty",
    "Douglas Emmett": "DEI|Douglas Emmett",
    "Hudson Pacific Properties": "HPP|Hudson Pacific",
    "Kimco Realty Corporation": "KIM|Kimco|Kimco Realty",
    "Alexandria Real Estate Equities": "ARE|Alexandria|Alexandria RE",
    "Tishman Speyer": "Tishman|Speyer",
    "Hines": "Hines|Hines Interests",
    "The Irvine Company": "Irvine|Irvine Company|TIC",
    "Related Companies": "Related|Related Companies",
    "Equity Residential": "EQR|Equity|Equity Residential",
    "AvalonBay Communities": "AVB|AvalonBay|Avalon",
    "Prologis": "PLD|Prologis|ProLogis",
    "Simon Property Group": "SPG|Simon|Simon Malls",
    "Westfield": "Westfield|WFD|Westfield Malls",
    "Macerich": "MAC|Macerich|Macerich Malls",
    "Federal Realty": "FRT|Federal|Federal Realty",
    "Regency Centers": "REG|Regency|Regency Centers",
    "Digital Realty": "DLR|Digital|Digital Realty",
    "Equinix": "EQIX|Equinix|Data Centers",
    "Ventas": "VTR|Ventas|Healthcare REIT",
    "Welltower": "WELL|Welltower|Senior REIT",
    "Healthcare Realty": "HR|Healthcare|Healthcare Realty",
    "Healthpeak Properties": "PEAK|Healthpeak|Healthcare Properties",
    "Host Hotels & Resorts": "HST|Host|Host Hotels",
    "Park Hotels & Resorts": "PK|Park Hotels|Park Resorts",
    "RLJ Lodging Trust": "RLJ|RLJ Lodging",
    "Apple Hospitality REIT": "APLE|Apple Hospitality",
    "Ashford Hospitality Trust": "AHT|Ashford|Ashford Hospitality",
    "Empire State Realty Trust": "ESRT|Empire State|Empire",
    "Paramount Group": "PGRE|Paramount|Paramount Group",
    "JBG Smith Properties": "JBGS|JBG|JBG Smith",
    "Brandywine Realty Trust": "BDN|Brandywine|Brandywine Realty",
    "Highwoods Properties": "HIW|Highwoods",
    "Cousins Properties": "CUZ|Cousins",
    "Piedmont Office Realty Trust": "PDM|Piedmont|Piedmont Office",
    "Columbia Property Trust": "CXP|Columbia|Columbia Property",
    "Office Properties Income Trust": "OPI|Office Properties",
    "Easterly Government Properties": "DEA|Easterly|Government Properties",
    "Acadia Realty Trust": "AKR|Acadia|Acadia Realty",
    "Principal Real Estate Investors": "PREI|Principal|Principal RE",
    "Apollo Global Management": "APO|Apollo",
    "Cerberus Capital": "Cerberus|Cerberus Capital",
    "Fortress Investment Group": "FIG|Fortress",
    "Starwood Capital": "Starwood|Starwood Capital",
    "Carlyle Group": "CG|Carlyle",
    "KKR": "KKR|Kohlberg Kravis",
    "TPG Capital": "TPG|Texas Pacific",

    # =========================================================================
    # HOTELS & HOSPITALITY
    # =========================================================================

    "Marriott": "Marriott|Marriott Hotels|Marriott International|Courtyard|Residence Inn|Ritz Carlton|W Hotels|Westin|Sheraton|St Regis|JW Marriott|Fairfield|SpringHill|TownePlace",
    "Hilton": "Hilton|Hilton Hotels|Conrad|Waldorf|DoubleTree|Embassy Suites|Hampton|Hampton Inn|Hilton Garden|Homewood|Home2|Curio|Tapestry|Tru|LXR",
    "InterContinental Hotels Group (IHG)": "IHG|InterContinental|Holiday Inn|Crowne Plaza|Kimpton|Indigo|Even Hotels|Staybridge|Candlewood",
    "Hyatt": "Hyatt|Hyatt Hotels|Park Hyatt|Grand Hyatt|Andaz|Hyatt Regency|Hyatt Place|Hyatt House|Thompson|Alila",
    "Wyndham": "Wyndham|Wyndham Hotels|Days Inn|Super 8|Ramada|La Quinta|Microtel|Wingate|Baymont|Howard Johnson|Travelodge",
    "Choice Hotels": "Choice|Choice Hotels|Comfort Inn|Comfort Suites|Quality Inn|Sleep Inn|Clarion|Econo Lodge|Rodeway|Cambria|Ascend",
    "Best Western": "Best Western|BW|Best Western Plus|Best Western Premier|SureStay",
    "Extended Stay America": "Extended Stay|ESA",
    "Sonesta International Hotels": "Sonesta|Sonesta Hotels",

    # =========================================================================
    # RETAIL & RESTAURANTS
    # =========================================================================

    "Walmart": "Walmart|Wal-Mart|Wal Mart|WMT|Sam's Club|Sams",
    "Target": "Target|TGT|Tar-jay|Bullseye",
    "Costco": "Costco|COST|Costco Wholesale",
    "The Home Depot": "Home Depot|HD|THD",
    "Lowe's": "Lowes|Lowe's|LOW",
    "Kroger": "Kroger|KR|Ralphs|Fred Meyer|Harris Teeter|Fry's|Smith's|King Soopers|QFC",
    "Albertsons Companies": "Albertsons|ACI|Safeway|Vons|Pavilions|Jewel-Osco|Acme|Shaw's|Tom Thumb|Randalls",
    "Macy's": "Macys|Macy's|M|Bloomingdales|Bloomies",
    "Nordstrom": "Nordstrom|JWN|Nordstrom Rack",
    "Jcpenney": "JCPenney|JCP|Penney's|Penneys",
    "Kohl's": "Kohls|Kohl's|KSS",
    "TJX Companies": "TJX|TJ Maxx|TJMaxx|Marshalls|HomeGoods|Home Goods|Sierra",
    "Ross Stores": "Ross|ROST|Ross Dress For Less|DD's",
    "Burlington Stores": "Burlington|BURL|Burlington Coat Factory",
    "Best Buy": "Best Buy|BBY|Geek Squad",
    "CVS Health": "CVS|CVS Health|CVS Pharmacy|Caremark",
    "Walgreens": "Walgreens|WBA|Duane Reade",
    "Rite Aid": "Rite Aid|RAD|Rite-Aid",
    "Dollar Tree": "Dollar Tree|DLTR|Family Dollar",
    "Dollar General": "Dollar General|DG",
    "Starbucks": "Starbucks|SBUX|Sbux|Coffee",
    "McDonald's": "McDonalds|McDonald's|MCD|Mickey D's|Golden Arches",
    "Subway": "Subway|Sub",
    "Chipotle Mexican Grill": "Chipotle|CMG|Mexican Grill",

    # =========================================================================
    # TECH COMPANIES
    # =========================================================================

    "Google": "Google|GOOG|GOOGL|Alphabet|YouTube|GCP|Google Cloud",
    "Amazon": "Amazon|AMZN|AWS|Amazon Web Services|Whole Foods|Prime",
    "Apple Inc": "Apple|AAPL|Mac|iPhone|Cupertino",
    "Microsoft": "Microsoft|MSFT|Azure|Windows|Office|LinkedIn|GitHub",
    "Meta": "Meta|Facebook|FB|Instagram|WhatsApp|Oculus",
    "Oracle": "Oracle|ORCL|Java|MySQL",
    "Salesforce": "Salesforce|CRM|SFDC",
    "Adobe": "Adobe|ADBE|Photoshop|Creative Cloud",
    "Intel": "Intel|INTC|Chipmaker",
    "Cisco": "Cisco|CSCO|Networking",
    "IBM": "IBM|International Business Machines|Big Blue",
    "Dell": "Dell|DELL|Dell Technologies|EMC",
    "HP": "HP|Hewlett Packard|HPE|HPQ",
    "VMware": "VMware|VMW|Virtualization",
    "SAP": "SAP|SAP SE|Enterprise Software",
    "ServiceNow": "ServiceNow|NOW|SNOW",
    "Workday": "Workday|WDAY",
    "Splunk": "Splunk|SPLK",
    "Databricks": "Databricks|Data|Analytics",
    "Snowflake": "Snowflake|SNOW|Data Cloud",
    "Palantir": "Palantir|PLTR",

    # =========================================================================
    # BANKS & FINANCIAL
    # =========================================================================

    "JPMorgan Chase (JPM)": "JPM|JPMorgan|JP Morgan|Chase|J.P. Morgan",
    "Bank of America": "BofA|Bank of America|BAC|BoA|Merrill|Merrill Lynch",
    "Wells Fargo": "Wells|Wells Fargo|WFC",
    "Citigroup": "Citi|Citigroup|C|Citibank",
    "Goldman Sachs": "Goldman|GS|Goldman Sachs",
    "Morgan Stanley": "Morgan Stanley|MS",
    "US Bank": "US Bank|USB|US Bancorp",
    "TD Bank": "TD|TD Bank|Toronto Dominion",
    "PNC": "PNC|PNC Bank|Pittsburgh National",
    "Capital One": "Capital One|COF|Cap One",
    "Truist": "Truist|TFC|BB&T|SunTrust",
    "Charles Schwab": "Schwab|SCHW|Charles Schwab",
    "State Street": "State Street|STT",
    "BNY Mellon": "BNY|Bank of New York|Mellon",
    "MetLife": "MetLife|MET",
    "Prudential": "Prudential|PRU",
    "AIG": "AIG|American International Group",
    "State Farm": "State Farm|State Farm Insurance",
    "Allstate": "Allstate|ALL",
    "Progressive": "Progressive|PGR",
    "GEICO": "GEICO|Government Employees Insurance",
    "New York Life Insurance Company": "NY Life|New York Life|NYL",
    "Northwestern Mutual": "Northwestern Mutual|NM|NML",
    "TIAA": "TIAA|TIAA-CREF|Teachers Insurance",
    "Fidelity": "Fidelity|Fidelity Investments",
    "Vanguard": "Vanguard|Vanguard Group",
    "BlackRock": "BlackRock|BLK",
    "T. Rowe Price": "T Rowe|T. Rowe Price|TROW",
    "Franklin Templeton": "Franklin|Franklin Templeton|BEN",

    # =========================================================================
    # TELECOMMUNICATIONS
    # =========================================================================

    "AT&T": "ATT|AT&T|AT and T|American Telephone|T|SBC|Southwestern Bell",
    "Verizon": "Verizon|VZ|Verizon Wireless",
    "T-Mobile": "T-Mobile|TMobile|TMUS|Magenta|Sprint",
    "Comcast": "Comcast|CMCSA|Xfinity|NBC|Universal",
    "Charter Communications": "Charter|CHTR|Spectrum|Time Warner Cable",
    "CenturyLink": "CenturyLink|CTL|Lumen|Level 3",
    "Cox Communications": "Cox|Cox Communications",
    "Altice": "Altice|Optimum|Suddenlink",
    "Frontier": "Frontier|FTR|Frontier Communications",
    "Windstream": "Windstream|WIN|Kinetic",

    # =========================================================================
    # HEALTHCARE & HOSPITALS
    # =========================================================================

    "Kaiser Permanente": "Kaiser|KP|Kaiser Permanente",
    "Sutter Health": "Sutter|Sutter Health",
    "Providence Health": "Providence|Providence Health|Swedish",
    "Dignity Health": "Dignity|Dignity Health|CommonSpirit",
    "HCA Healthcare": "HCA|HCA Healthcare|Hospital Corporation",
    "Tenet Healthcare": "Tenet|THC|Tenet Healthcare",
    "Community Health Systems": "CHS|Community Health",
    "Universal Health Services": "UHS|Universal Health",
    "Ascension": "Ascension|Ascension Health",
    "Trinity Health": "Trinity|Trinity Health",
    "Adventist Hospital": "Adventist|AdventHealth|Advent",
    "Scripps Health": "Scripps|Scripps Health",
    "Sharp HealthCare": "Sharp|Sharp Healthcare",
    "Mount Sinai Health System": "Mount Sinai|Sinai|Mt Sinai",
    "NewYork-Presbyterian": "NYP|NY Presbyterian|New York Presbyterian|Presbyterian",
    "Memorial Sloan Kettering": "MSK|Sloan Kettering|Memorial Sloan|Sloan",
    "Cleveland Clinic": "Cleveland Clinic|CCF",
    "Mayo Clinic": "Mayo|Mayo Clinic",
    "Johns Hopkins Hospital": "Johns Hopkins|Hopkins|JHU Hospital",
    "Massachusetts General Hospital": "MGH|Mass General",
    "Brigham And Women's Hospital": "BWH|Brigham|Brigham and Women's",
    "UCLA Medical Center": "UCLA Medical|UCLA Hospital|Ronald Reagan",
    "UCSF Medical Center": "UCSF Medical|UCSF Hospital",
    "Stanford Hospital": "Stanford Hospital|Stanford Medical",
    "Cedars-Sinai": "Cedars|Cedars-Sinai|Cedars Sinai",
    "Rush University Medical Center (RUMC)": "Rush|RUMC|Rush Medical|Rush Hospital",
    "Northwestern Memorial Hospital": "Northwestern Memorial|NMH",
    "UChicago Medicine": "UChicago Medicine|University of Chicago Hospital",
    "Boston Medical Center": "BMC|Boston Medical",
    "Beth Israel Deaconess Medical Center": "BIDMC|Beth Israel|BI",

    # =========================================================================
    # SCHOOL DISTRICTS
    # =========================================================================

    "Chicago Public Schools": "CPS|Chicago Public|Chicago Schools",
    "Los Angeles Unified School District": "LAUSD|LA Unified|Los Angeles Schools|LA Schools",
    "New York City Geographic District": "NYCGED|NYC Schools|New York Schools|DOE",
    "District Of Columbia Public Schools": "DCPS|DC Public Schools|DC Schools|Washington Schools",
    "Seattle Public Schools": "SPS|Seattle Schools",
    "San Diego Unified School District": "SDUSD|San Diego Schools|SD Schools",
    "San Francisco Unified School District": "SFUSD|SF Schools|San Francisco Schools",
    "Denver Public Schools": "DPS|Denver Schools",
    "Boston Public Schools": "BPS|Boston Schools",
    "Philadelphia Public Schools": "PPS|Philadelphia Schools|Philly Schools",
    "Houston Independent School District": "HISD|Houston Schools|Houston ISD",
    "Dallas Independent School District": "DISD|Dallas Schools|Dallas ISD",
    "School District of Philadelphia": "SDP|Philadelphia Schools|Philly Schools",
    "The School District Of Kcmo": "KCMO|Kansas City Schools|KC Schools",

    # =========================================================================
    # ORGANIZATIONS & NONPROFITS
    # =========================================================================

    "Young Men's Christian Association (YMCA)": "YMCA|Y|The Y|YM",
    "Young Women's Christian Association (YWCA)": "YWCA|YW",
    "The Salvation Army": "Salvation Army|SA|Sally Ann",
    "Goodwill": "Goodwill|GW",
    "Roman Catholic Church": "Catholic|Catholic Church|Archdiocese|Diocese",
    "United Methodist Church": "Methodist|United Methodist|UMC",
    "Baptist Church": "Baptist|Southern Baptist|SBC",
    "Presbyterian Church": "Presbyterian|PCUSA|PCA",
    "Episcopal Church": "Episcopal|Episcopalian",
    "Lutheran Church": "Lutheran|ELCA|LCMS",
    "Jewish Federation": "Jewish|Federation|JCC",

    # =========================================================================
    # TRANSPORTATION & LOGISTICS
    # =========================================================================

    "United Airlines": "United|UA|UAL|United Airlines",
    "American Airlines": "American|AA|AAL|American Airlines",
    "Delta Air Lines": "Delta|DAL|Delta Airlines",
    "Southwest Airlines": "Southwest|WN|LUV|Southwest Airlines",
    "JetBlue Airways": "JetBlue|JBLU|JetBlue Airways",
    "Alaska Airlines": "Alaska|AS|ALK|Alaska Airlines",
    "Spirit Airlines": "Spirit|SAVE|Spirit Airlines",
    "Frontier Airlines": "Frontier|F9|Frontier Airlines",
    "FedEx": "FedEx|FDX|Federal Express",
    "UPS": "UPS|United Parcel|United Parcel Service",
    "DHL": "DHL|Deutsche Post",
    "USPS": "USPS|Postal Service|Post Office|Mail",
    "Los Angeles World Airports": "LAWA|LAX|Los Angeles Airports|LA Airports",
    "Port Authority Of New York And New Jersey": "PANYNJ|Port Authority|JFK|Newark|LaGuardia|LGA|EWR",
    "Port Of Seattle": "Port of Seattle|Sea-Tac|SeaTac",
    "Port Of Los Angeles": "POLA|Port of LA|LA Port|San Pedro",
    "Port Of Long Beach": "POLB|Port of LB|Long Beach Port",

    # =========================================================================
    # ADDITIONAL ABBREVIATIONS FOR EXISTING ORGS
    # =========================================================================

    "PGIM": "PGIM|Prudential Investment|PIM",
    "DWS Group": "DWS|DWS Group|Deutsche Asset",
    "CIM Group": "CIM|CIM Group",
    "GFP Real Estate": "GFP|GFP Real Estate",
    "RFR Realty": "RFR|RFR Realty",
    "RXR Realty": "RXR|RXR Realty",
    "Wework": "WeWork|We Work|WW",
    "AMC Entertainment Holdings, Inc. (AMC)": "AMC|AMC Theatres|AMC Theaters|AMC Entertainment",
    "Regal Entertainment": "Regal|Regal Cinemas|Regal Theatres",
    "Cinemark Holdings": "Cinemark|CNK|Cinemark Theatres",
    "California Department of Transportation (Caltrans)": "Caltrans|CA DOT|California DOT|Cal Trans",
}

# =============================================================================
# AUTO-GENERATION PATTERNS
# =============================================================================

def generate_auto_aliases(org_name, display_name):
    """Generate automatic aliases from common patterns."""
    aliases = set()
    name_lower = org_name.lower()

    # Extract acronym from parentheses like "New York University (NYU)"
    acronym_match = re.search(r'\(([A-Z]{2,})\)', org_name)
    if acronym_match:
        aliases.add(acronym_match.group(1))

    # "University of X" → "U of X", "UX"
    if 'university of' in name_lower:
        place = name_lower.split('university of')[-1].strip()
        aliases.add(f"u of {place}")
        aliases.add(f"u of {place.split()[0]}" if ' ' in place else f"u{place[0]}")
        # Get initials
        words = place.split()
        if len(words) >= 1:
            aliases.add('u' + ''.join(w[0] for w in words))

    # "X University" → "XU"
    if name_lower.endswith(' university') and 'of' not in name_lower:
        place = name_lower.replace(' university', '')
        words = place.split()
        if len(words) >= 1:
            aliases.add(''.join(w[0] for w in words) + 'u')

    # "City Of X" → city name and common abbrevs
    if name_lower.startswith('city of '):
        city = name_lower.replace('city of ', '')
        aliases.add(city)
        # City-specific abbreviations handled in MANUAL_ALIASES

    # "State Of X" → state name
    if name_lower.startswith('state of '):
        state = name_lower.replace('state of ', '')
        aliases.add(state)

    # "X County" → county name
    if name_lower.endswith(' county'):
        county = name_lower.replace(' county', '')
        aliases.add(county)

    # "Department Of X" → DOX abbreviation
    if name_lower.startswith('department of '):
        dept = name_lower.replace('department of ', '')
        words = dept.split()
        if len(words) >= 1:
            aliases.add('d' + ''.join(w[0] for w in words if len(w) > 2))

    # School district patterns
    if 'unified school district' in name_lower:
        city = name_lower.replace(' unified school district', '')
        aliases.add(f"{city} schools")
        aliases.add(f"{city} usd")

    if 'public schools' in name_lower:
        city = name_lower.replace(' public schools', '')
        aliases.add(f"{city} schools")

    # Add display_name if different
    if display_name and display_name.lower() != org_name.lower():
        aliases.add(display_name.lower())

    return aliases

# =============================================================================
# MAIN PROCESSING
# =============================================================================

def main():
    # Load existing CSV
    csv_path = str(PORTFOLIO_ORGS_PATH)
    df = pd.read_csv(csv_path)

    print(f"Loaded {len(df)} organizations")

    # Build search_aliases column
    all_aliases = []

    for idx, row in df.iterrows():
        org_name = str(row.get('organization', ''))
        display_name = str(row.get('display_name', ''))

        aliases = set()

        # Add manual aliases if we have them
        if org_name in MANUAL_ALIASES:
            manual = MANUAL_ALIASES[org_name].split('|')
            aliases.update(a.strip() for a in manual if a.strip())

        # Also check variations of the name
        for manual_name, manual_aliases in MANUAL_ALIASES.items():
            if manual_name.lower() in org_name.lower() or org_name.lower() in manual_name.lower():
                if manual_name != org_name:  # Don't double-add exact matches
                    # Check if it's a close enough match
                    if len(manual_name) > 10 and (manual_name.lower() in org_name.lower() or org_name.lower() in manual_name.lower()):
                        aliases.update(a.strip() for a in manual_aliases.split('|') if a.strip())

        # Add auto-generated aliases
        auto = generate_auto_aliases(org_name, display_name)
        aliases.update(auto)

        # Add display_name
        if display_name and display_name.lower() != org_name.lower():
            aliases.add(display_name)

        # Clean up aliases
        aliases = [a for a in aliases if a and len(a) >= 2]
        aliases = sorted(set(aliases), key=str.lower)

        # Join with pipe
        alias_str = '|'.join(aliases) if aliases else ''
        all_aliases.append(alias_str)

        if idx < 20 or (aliases and idx % 100 == 0):
            print(f"  {org_name[:50]}: {len(aliases)} aliases")

    # Add column to dataframe
    df['search_aliases'] = all_aliases

    # Save
    df.to_csv(csv_path, index=False)
    print(f"\nSaved {len(df)} organizations with search_aliases to {csv_path}")

    # Stats
    orgs_with_aliases = sum(1 for a in all_aliases if a)
    total_aliases = sum(len(a.split('|')) for a in all_aliases if a)
    print(f"Organizations with aliases: {orgs_with_aliases}")
    print(f"Total aliases added: {total_aliases}")

if __name__ == '__main__':
    main()
