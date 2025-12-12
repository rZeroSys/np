#!/usr/bin/env python3
"""
Download missing logos and update portfolio_orgs.csv
"""

import requests
import csv
import os
from io import BytesIO
from PIL import Image
import time

LOGO_DIR = '/Users/forrestmiller/Desktop/Final real/Logos'
CSV_PATH = '/Users/forrestmiller/Desktop/Final real/portfolio_orgs.csv'

# Mapping of org names to logo URLs (from user-provided list)
LOGO_URLS = {
    "Jenel Management": "https://static.wixstatic.com/media/9f2361_b42f47d99f6e4ee8b13112404f782d2c~mv2_d_14530_8684_s_6_4_3.png/v1/fill/w_240,h_143,al_c,usm_0.66_1.00_0.01/9f2361_b42f47d99f6e4ee8b13112404f782d2c~mv2_d_14530_8684_s_6_4_3.png",
    "Elo Realty": "https://lookaside.fbsbx.com/lookaside/crawler/media/?media_id=497301229063407",
    "Charles Dunn Real Estate Services": "https://www.charlesdunn.com/wp-content/uploads/2025/03/chales-dunn-1024x538.png",
    "Prospect Health System": "https://mma.prnewswire.com/media/1885060/Prospect_Stacked.jpg?p=facebook",
    "DWS RREEF": "https://picante.today/wp-content/uploads/2023/01/289678-the-new-germany-fund-inc-announces-portfolio-manager-changes.jpg",
    "First Pioneer Properties": "https://firstpioneerproperties.com/wp-content/uploads/102-West-38th_004_v2_crop-660x392.jpg",
    "Health Sciences High District": "https://lookaside.fbsbx.com/lookaside/crawler/media/?media_id=100054225740930",
    "Kf Braun": "https://media.licdn.com/dms/image/v2/C4E1BAQGVJ8an4mGOCQ/company-background_10000/company-background_10000/0/1585346958128/braun_management_inc_cover?e=2147483647&v=beta&t=sXwtn2krT3_iX1mogTog1N4YEnsmJi0a1M8LYhA9tbU",
    "Stephens Institute": "https://web.stevens.edu/news/newspoints/brand-logos/Stevens-ducks-mascott-Attila.png",
    "Health Sciences Middle District": "https://lookaside.fbsbx.com/lookaside/crawler/media/?media_id=100054225740930",
    "Gelb Enterprises": "https://images.squarespace-cdn.com/content/v1/61dc946771a78b76105898da/3bd211eb-3576-4bcc-ac04-011707d50a2f/neghro+Logo.png?format=1500w",
    "California Education Authority": "https://cdn.edmentum.com/assets/photo/overview/California-Seal-Approval.png",
    "Savanna Elementary": "https://www.dentonisd.org/cms/lib/TX21000245/Centricity/Template/GlobalAssets/images///logos/Savannah_Gators_2017_rgb.png",
    "Are-Ma Region No. 38 LLC": "https://emgality.lilly.com/assets/images/emgality-logo.png",
    "Fortune District": "https://fortune.com/img-assets/wp-content/uploads/2023/08/Fortune-Global-500-logo-e1690922780643.jpg?w=1440&q=75",
    "Crown Power & Redevelopment CORP": "https://crownpower.s3.us-east-2.amazonaws.com/crownpower/wp-content/uploads/2023/06/hustler-e1687535049869.png",
    "Hamilton Landing": "https://lirp.cdn-website.com/ca63c9eb/dms3rep/multi/opt/Hamilton+Landing+Mulberry-354w.png",
    "Broadway Square Partners LLP": "https://dynamic-media-cdn.tripadvisor.com/media/photo-o/18/a6/70/18/broadway-square.jpg?w=1200&h=-1&s=1",
    "Fred Hutchinson Cancer Center (Fred Hutch)": "https://upload.wikimedia.org/wikipedia/commons/e/e8/Fred-Hutch-Logo-Stacked.png",
    "Kenneth Aschendorf and Berndt Perl": "https://media.licdn.com/dms/image/v2/D4E22AQGXN3tSr4hpeQ/feedshare-shrink_800/B4EZRgj1noGwAg-/0/1736786795370?e=2147483647&v=beta&t=a0aavK7GwwSTaPj7KAKaxS2Vifcj9gXLkW2I_esHHgM",
    "Office Depot/Officemax": "https://1000logos.net/wp-content/uploads/2025/05/Office-Depot-Logo-2013.png",
    "Global Holdings": "https://media-cldnry.s-nbcnews.com/image/upload/t_fit-760w,f_auto,q_auto:best/streams/2012/November/121115/1C4777941-111115_mfglobal_hmed_1112p.jpg",
    "Eq Management LLC": "https://www.atlasholdingsllc.com/wp-content/uploads/2022/08/EQI-Logo-Color-v2-01-312x236.jpg",
    "Classical Academy High District": "https://coloradoleague.org/static/8aa84800-8f3d-4bb0-956a556a939a4754/opengraphimage_83f4e8796336604b59d7216d0ecd81a5_4a7c7e45a350/TCA-College-Pathways.png",
    "Mojave River Academy - Marble City District": "http://www.mojaveriver.net/pics/OROGSD-MORA_LOGO.gif",
    "Windsor Mgmt": "https://windsorm.com/wp-content/uploads/2025/04/cropped-Windsor_Social_Card.jpg",
    "Hd Development Of Maryland, INC.": "https://news.maryland.gov/dhcd/wp-content/uploads/sites/16/2025/07/2025-Press-Release-Featured-Image-1.png",
    "RFR Holdings": "https://mma.prnewswire.com/media/2210435/RFR_Logo.jpg?w=300",
    "High Tech Elementary Mesa District": "https://www.hightechhigh.org/htem/wp-content/uploads/sites/17/2025/07/070225_HTe_mesa_stacked_fullcolor_RGB.svg",
    "John Henry High District": "http://www.amethodschools.org/ourpages/auto/2018/6/5/45386445/rca%20top%20bay%20area%20school.jpg",
    "Bonafide Estates": "https://media-production.lp-cdn.com/cdn-cgi/image/format=auto,quality=85/https://media-production.lp-cdn.com/media/h9yfgmq2ej5x2qulbvvs",
    "San Diego 2 LLC.": "https://images.mlssoccer.com/image/private/t_editorial_landscape_12_desktop/mls-sdn/xmq38w53mytvvy3gk3mn.jpg",
    "S. C. Herman & Associates, INC.": "https://images.squarespace-cdn.com/content/v1/52d3fd1de4b0eab6f2d7674a/fcbc61aa-78e2-46c2-8ad9-f9c6813df330/1120%2BVermont%2BAvenue%2C%2BNW%2B-%2BExt%2B%2832%29.JPG?format=2500w",
    "California Department of General Services (CA-DGS)": "https://sdivsbdc.org/wp-content/uploads/2022/08/dgs-california-department-of-general-services-logo-vector.png",
    "Hudson Gateway Place, LLC": "https://irp.cdn-website.com/a5e60d20/dms3rep/multi/Good+Cause+Eviction-2.png",
    "Boys Club Of Boston INC Mass": "https://www.bgcb.org/wp-content/uploads/2024/11/social.png",
    "A Trenkmann Est INC": "https://extra-images.akamaized.net/image/26/4by3/2024/03/15/269eac33893e4c00935925a4a8f34f83_xl.jpg",
    "Quadrangle Management Company": "https://www.quadrangledevelopment.com/wp-content/uploads/2023/04/socialpreview_quadrangle.jpg",
    "USL Property Management": "https://cdn1.sportngin.com/attachments/news_article/50a2-203163100/USL-Partnership-Scandanavian-WEB_1_large.png",
    "Ruthenium LLC": "https://i.ebayimg.com/images/g/ZmUAAOSw73Natdud/s-l1200.jpg",
    "JEMB Realty": "https://www.jembrealty.com/wp-content/uploads/2020/09/big.jpg",
    "RB Properties, Inc.": "https://www.rbpropertiesinc.com/resourcefiles/mainimages/rb-properties-inc-about-us-top.jpg?version=6162025104849",
    "Southeastern Pennsylvania Transportation Authority (SEPTA)": "https://campusphilly.org/wp-content/uploads/2023/08/septa-og-fb.jpg",
    "United States Postal Service (USPS)": "https://logos-world.net/wp-content/uploads/2020/10/United-States-Postal-Service-Logo.png",
    "Monarchs Sub, LLC": "https://cdngeneral.rentcafe.com/dmslivecafe/3/2134978/logo_citrine_2__2(20250811180306170).png?width=480&quality=90",
    "Wolet Enterprises": "https://brandlogos.net/wp-content/uploads/2025/05/wolt-logo_brandlogos.net_dijtc.png",
    "Aurora Capital Associates": "https://images.squarespace-cdn.com/content/v1/63e15137967c4254693e3e86/9ec2e715-e31b-4f9f-8d51-d9fda461b562/Logo-3_4x-100-scaled.jpg?format=1500w",
    "Saint Joseph's University": "https://www.sju.edu/sites/mergersjuedu/files/styles/16_9_320x180/public/BS---03---SJU.jpg?h=8abcec71&itok=pKKG06ah",
    "Aspen Valley Prep Academy District": "https://valley.aspenps.org/wp-content/uploads/2025/04/APS-Valley-Logo-Mark-Color.svg",
    "Curtis Investment Group": "https://d2kcmk0r62r1qk.cloudfront.net/imageDevelopers/Logo/635881071477316000_curtisinvestmentgroup_logo.jpg",
    "United States Conference Of Catholic Bishops": "https://lookaside.fbsbx.com/lookaside/crawler/media/?media_id=100063957708254",
    "Central Library": "https://www.sec.gov/Archives/edgar/data/1297996/000155837022007648/dlr-20220331xex10d5002.jpg",
    "New York City Geographic District # 8": "https://upload.wikimedia.org/wikipedia/en/thumb/7/7c/New_York_Public_Library_logo.svg/1200px-New_York_Public_Library_logo.svg.png",
    "Coppola Too Winery": "https://mma.prnewswire.com/media/777295/The_Family_Coppola_Rewards_Logo.jpg?p=facebook",
    "Bayshore Tech Park": "https://static.wixstatic.com/media/bfb491_cfd6b84d05854091b17a61f166a1be87~mv2.jpg/v1/fill/w_280,h_185,q_90,enc_avif,quality_auto/bfb491_cfd6b84d05854091b17a61f166a1be87~mv2.jpg",
    "Natomas Marketplace": "https://cdn-files.eu.placewise.com/files/lWAb1Xc1Ea5dXFh_gU1fDVbdT5Zxkj_7HdVEV0LfcsJSXLuoy2nIRw9USazcFDBUhvm6kq6-4au0muYsIxQielyIT4lNJfs4v_44gPpDWjhNdWJlTm1qb1g?transform=output=format:webp,quality:80/resize=width:1920,height:1920,fit:clip",
    "Brookings Institution": "https://www.brookings.edu/wp-content/uploads/2023/06/brookings-share-default.jpg?quality=75",
    "TELLURIUM": "https://telluriumq.com/wp-content/uploads/2020/07/Tellurium-Q.jpg",
    "Harvard Pacific (DCC)": "https://weadapt.org/wp-content/uploads/2023/05/768px-philippine_red_cross_emblem.svg_.png",
    "Des Moines Public Schools (Chicago)": "https://i.ytimg.com/vi/cl8PCZIwNqk/maxresdefault.jpg",
    "Pontegadea": "https://images.ft.com/v3/image/raw/http%3A%2F%2Fcom.ft.imagepublish.upp-prod-eu.s3.amazonaws.com%2F46a2f248-638c-11ea-b3f3-fe4680ea68b5?source=next-article&fit=scale-down&quality=highest&width=700&dpr=1",
    "Discovery Collection": "https://images2.minutemediacdn.com/image/upload/c_fill,w_720,ar_16:9,f_auto,q_auto,g_auto/shape/cover/sport/d52b42f2e8dbbde5fc261c84239301f9f2d70dac6caaabf832bce61e10daaa76.jpg",
    "Paramount Plaza, LLC": "https://upload.wikimedia.org/wikipedia/commons/e/e7/Paramount_Skydance_Logo.svg",
    "Cognac Del Mar Owner II, LLC": "https://resources.contracts.justia.com/contract-images/ea0def5de2ced4980693c342f5692582aae58a98.jpg",
    "The Davis Companies": "https://www.davisiga.com/wp-content/uploads/sites/102/2019/01/cropped-davis-logo-1.png",
    "Los Angeles Department Of Building And Safety": "https://iapmo.org/media/lr0ddgfa/ladbs-740.jpg?upscale=false&width=1200",
    "Investors HQ": "https://www.investorsomaha.com/wp-content/uploads/2024/01/A-Sign-On-Every-Mile_12.2023.png",
    "940 Alameda LLC": "https://images.squarespace-cdn.com/content/v1/5c564b9dca525b02bef29275/1750952104600-XFJ9JIFTY3M9OONY71D0/Edit+%2B+Logo.jpg?format=2500w",
    "Hh Prop LLC": "https://harpethpaintingllc.com/wp-content/smush-webp/2025/04/badge-2.png.webp",
    "Thrifty Oil/Orden Company": "https://media.licdn.com/dms/image/v2/D4E10AQHBSXXFY2-KpA/videocover-low/B4EZmXCV0YHoBE-/0/1759175602458/4oceanCorporateGiftingmp4?e=2147483647&v=beta&t=88nzG37tKfBQyOuDESD7ELCIKFGnxoCvI_zZRM4QhEU",
    "National Academy of Sciences": "https://upload.wikimedia.org/wikipedia/en/thumb/8/80/National_Academy_of_Sciences_logo.svg/1200px-National_Academy_of_Sciences_logo.svg.png",
    "The Buyers Market": "https://canadianautodealer.ca/wp-content/uploads/2024/12/4-KBB-1200.jpg",
    "Plaza Inv": "https://upload.wikimedia.org/wikipedia/en/2/22/Plaza_Hotel_logo.png",
    "Downtown Properties": "https://cityofsugarhill.com/wp-content/uploads/2025/02/Downtown-Logo-City-Logo-official.png",
    "West Side Realty": "https://static.wixstatic.com/media/897a57_954f4e4569284829bf91e7152bf8a8ab~mv2.png/v1/fill/w_1024,h_576,al_c/897a57_954f4e4569284829bf91e7152bf8a8ab~mv2.png",
    "San Diego Gas & Electric": "https://www.sdge.com/sites/default/files/WhyTheChange_logo.png",
}

# Also add the one exact match we found
LOGO_URLS["Albertsons Companies"] = None  # Already exists, just need to update CSV

def org_to_filename(org_name):
    """Convert org name to logo filename following the naming convention."""
    # Replace spaces with underscores, keep special chars
    filename = org_name.replace(' ', '_') + '.png'
    return filename

def download_and_save_logo(org_name, url):
    """Download logo from URL and save as PNG."""
    filename = org_to_filename(org_name)
    filepath = os.path.join(LOGO_DIR, filename)

    print(f"  [DOWNLOAD] Fetching: {url[:80]}...")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        # Handle SVG files specially
        if url.endswith('.svg') or 'svg' in response.headers.get('content-type', ''):
            print(f"  [WARN] SVG file detected, saving as-is (may need manual conversion)")
            svg_filepath = filepath.replace('.png', '.svg')
            with open(svg_filepath, 'wb') as f:
                f.write(response.content)
            print(f"  [SAVED] {svg_filepath}")
            return svg_filepath.split('/')[-1]

        # Try to open and convert to PNG
        img = Image.open(BytesIO(response.content))

        # Convert to RGB if necessary (for RGBA or P mode images)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGBA')
            # Create white background for transparency
            background = Image.new('RGBA', img.size, (255, 255, 255, 255))
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background.convert('RGB')
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        img.save(filepath, 'PNG')
        print(f"  [SAVED] {filepath}")
        return filename

    except Exception as e:
        print(f"  [ERROR] Failed to download {org_name}: {e}")
        return None

def update_csv():
    """Update the CSV file with new logo filenames."""
    print("\n" + "="*60)
    print("UPDATING CSV FILE")
    print("="*60)

    # Read existing CSV
    rows = []
    with open(CSV_PATH, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            rows.append(row)

    # Update rows with new logo filenames
    updated_count = 0
    for row in rows:
        org_name = row['organization_name']
        if org_name in LOGO_URLS:
            expected_filename = org_to_filename(org_name)
            logo_path = os.path.join(LOGO_DIR, expected_filename)

            # Check if logo file exists
            if os.path.exists(logo_path):
                if row['logo_file'] != expected_filename:
                    print(f"  [UPDATE] {org_name}: '' -> {expected_filename}")
                    row['logo_file'] = expected_filename
                    updated_count += 1
            else:
                # Check for SVG version
                svg_filename = expected_filename.replace('.png', '.svg')
                svg_path = os.path.join(LOGO_DIR, svg_filename)
                if os.path.exists(svg_path):
                    print(f"  [UPDATE] {org_name}: '' -> {svg_filename}")
                    row['logo_file'] = svg_filename
                    updated_count += 1

    # Write back to CSV
    with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n  Total CSV entries updated: {updated_count}")

def main():
    print("="*60)
    print("LOGO DOWNLOADER SCRIPT")
    print("="*60)
    print(f"Logo directory: {LOGO_DIR}")
    print(f"CSV file: {CSV_PATH}")
    print(f"Total orgs to process: {len(LOGO_URLS)}")
    print("="*60 + "\n")

    success_count = 0
    fail_count = 0
    skip_count = 0

    for i, (org_name, url) in enumerate(LOGO_URLS.items(), 1):
        print(f"\n[{i}/{len(LOGO_URLS)}] Processing: {org_name}")

        # Check if logo already exists
        expected_filename = org_to_filename(org_name)
        expected_path = os.path.join(LOGO_DIR, expected_filename)

        if os.path.exists(expected_path):
            print(f"  [SKIP] Logo already exists: {expected_filename}")
            skip_count += 1
            continue

        if url is None:
            print(f"  [SKIP] No URL provided (logo should already exist)")
            skip_count += 1
            continue

        result = download_and_save_logo(org_name, url)
        if result:
            success_count += 1
        else:
            fail_count += 1

        # Small delay to be nice to servers
        time.sleep(0.5)

    print("\n" + "="*60)
    print("DOWNLOAD SUMMARY")
    print("="*60)
    print(f"  Successful downloads: {success_count}")
    print(f"  Failed downloads: {fail_count}")
    print(f"  Skipped (already exist): {skip_count}")

    # Now update the CSV
    update_csv()

    print("\n" + "="*60)
    print("DONE!")
    print("="*60)

if __name__ == "__main__":
    main()
