#!/bin/bash
# Upload 53 broken logos to AWS S3 with cache-busting

# Array of files to upload (local path -> s3 key)
declare -a FILES=(
    "/Users/forrestmiller/Desktop/logos/Seattle_Public_Schools.png|logos/Seattle_Public_Schools.png"
    "/Users/forrestmiller/Desktop/logos/SEPHORA.png|logos/SEPHORA.png"
    "/Users/forrestmiller/Desktop/logos/Northwood_Investors.png|logos/Northwood_Investors.png"
    "/Users/forrestmiller/Desktop/logos/Oxford_Preparatory_Academy.png|logos/Oxford_Preparatory_Academy.png"
    "/Users/forrestmiller/Desktop/logos/S.C._Herman_Associates_Inc.png|logos/S.C._Herman_Associates_Inc.png"
    "/Users/forrestmiller/Desktop/logos/Gilead_Sciences.png|logos/Gilead_Sciences.png"
    "/Users/forrestmiller/Desktop/logos/Shulsky_Properties.png|logos/Shulsky_Properties.png"
    "/Users/forrestmiller/Desktop/logos/MJ_Orbach.png|logos/MJ_Orbach.png"
    "/Users/forrestmiller/Desktop/logos/UBS_Realty_Investors.png|logos/UBS_Realty_Investors.png"
    "/Users/forrestmiller/Desktop/logos/United_States_Conference_Of_Catholic_Bishops.png|logos/United_States_Conference_Of_Catholic_Bishops.png"
    "/Users/forrestmiller/Desktop/logos/Integris_Ventures.png|logos/Integris_Ventures.png"
    "/Users/forrestmiller/Desktop/logos/COPT_Defense_Properties.png|logos/COPT_Defense_Properties.png"
    "/Users/forrestmiller/Desktop/logos/Wagner_College.png|logos/Wagner_College.png"
    "/Users/forrestmiller/Desktop/logos/Santa_Rosa_Junior_College.png|logos/Santa_Rosa_Junior_College.png"
    "/Users/forrestmiller/Desktop/logos/St_Josephs_College.png|logos/St_Josephs_College.png"
    "/Users/forrestmiller/Desktop/logos/St_Pauls_Senior_Services.png|logos/St_Pauls_Senior_Services.png"
    "/Users/forrestmiller/Desktop/logos/American_Chemical_Society.png|logos/American_Chemical_Society.png"
    "/Users/forrestmiller/Desktop/logos/Nightingale_Properties_LLC.png|logos/Nightingale_Properties_LLC.png"
    "/Users/forrestmiller/Desktop/logos/USL_Property_Management.png|logos/USL_Property_Management.png"
    "/Users/forrestmiller/Desktop/logos/International_Brotherhood_Of_Teamsters.png|logos/International_Brotherhood_Of_Teamsters.png"
    "/Users/forrestmiller/Desktop/logos/Barnard_College.png|logos/Barnard_College.png"
    "/Users/forrestmiller/Desktop/logos/Pepperdine_University.png|logos/Pepperdine_University.png"
    "/Users/forrestmiller/Desktop/logos/Mission_Language_And_Vocational_School.png|logos/Mission_Language_And_Vocational_School.png"
    "/Users/forrestmiller/Desktop/logos/Las_Positas_College.png|logos/Las_Positas_College.png"
    "/Users/forrestmiller/Desktop/logos/Palomar_College.png|logos/Palomar_College.png"
    "/Users/forrestmiller/Desktop/logos/Pacific_Northwest_College_Of_Art.png|logos/Pacific_Northwest_College_Of_Art.png"
    "/Users/forrestmiller/Desktop/logos/Boston_Symphony_Orchestra.png|logos/Boston_Symphony_Orchestra.png"
    "/Users/forrestmiller/Desktop/logos/City_Of_San_Diego.png|logos/City_Of_San_Diego.png"
    "/Users/forrestmiller/Desktop/logos/LVMH_Mo_t_Hennessy_Louis_Vuitton_LVMH.png|logos/LVMH_Mo_t_Hennessy_Louis_Vuitton_LVMH.png"
    "/Users/forrestmiller/Desktop/logos/The_Hearn_Company.png|logos/The_Hearn_Company.png"
    "/Users/forrestmiller/Desktop/logos/Affiliated_Engineers_NW_Inc.png|logos/Affiliated_Engineers_NW_Inc.png"
    "/Users/forrestmiller/Desktop/logos/Feldman_Realty_Group.png|logos/Feldman_Realty_Group.png"
    "/Users/forrestmiller/Desktop/logos/San_Diego_State_University.png|logos/San_Diego_State_University.png"
    "/Users/forrestmiller/Desktop/logos/Daimler_Truck_North_America.png|logos/Daimler_Truck_North_America.png"
    "/Users/forrestmiller/Desktop/logos/Multi-Employer_Property_Trust_MEPT.png|logos/Multi-Employer_Property_Trust_MEPT.png"
    "/Users/forrestmiller/Desktop/logos/Skyline_College.png|logos/Skyline_College.png"
    "/Users/forrestmiller/Desktop/logos/Solheim_Senior_Community.png|logos/Solheim_Senior_Community.png"
    "/Users/forrestmiller/Desktop/logos/Found_Study.png|logos/Found_Study.png"
    "/Users/forrestmiller/Desktop/logos/The_Ashtin_Group_Inc.png|logos/The_Ashtin_Group_Inc.png"
    "/Users/forrestmiller/Desktop/logos/Takara_Bio_USA_Holdings_Inc.png|logos/Takara_Bio_USA_Holdings_Inc.png"
    "/Users/forrestmiller/Desktop/logos/Artesia_Christian_Home.png|logos/Artesia_Christian_Home.png"
    "/Users/forrestmiller/Desktop/logos/Finishing_Trades_Institute.png|logos/Finishing_Trades_Institute.png"
    "/Users/forrestmiller/Desktop/logos/Devry_University.png|logos/Devry_University.png"
    "/Users/forrestmiller/Desktop/logos/Claremont_Colleges.png|logos/Claremont_Colleges.png"
    "/Users/forrestmiller/Desktop/logos/Association_Of_American_Medical_Colleges.png|logos/Association_Of_American_Medical_Colleges.png"
    "/Users/forrestmiller/Desktop/logos/PAE_Consulting_Engineers_PAE.png|logos/PAE_Consulting_Engineers_PAE.png"
    "/Users/forrestmiller/Desktop/logos/Gordon_Property_Group_LLC.png|logos/Gordon_Property_Group_LLC.png"
    "/Users/forrestmiller/Desktop/logos/City_Of_Hope.png|logos/City_Of_Hope.png"
    "/Users/forrestmiller/Desktop/logos/Ganahl_Lumber.png|logos/Ganahl_Lumber.png"
    "/Users/forrestmiller/Desktop/logos/Akf3_Valencia_LLC.png|logos/Akf3_Valencia_LLC.png"
    "/Users/forrestmiller/Desktop/logos/Exchange_Boulevard_One.png|logos/Exchange_Boulevard_One.png"
    "/Users/forrestmiller/Desktop/logos/Harkins_Theatres_Northfield_18.png|logos/Harkins_Theatres_Northfield_18.png"
    "/Users/forrestmiller/Desktop/logos/Sierra_College.png|logos/Sierra.png"
)

BUCKET="nationwide-odcv-images"
TOTAL=${#FILES[@]}
SUCCESS=0
FAIL=0

echo "Uploading $TOTAL logos to s3://$BUCKET"
echo "========================================"

for item in "${FILES[@]}"; do
    LOCAL="${item%%|*}"
    S3KEY="${item##*|}"
    FNAME=$(basename "$LOCAL")

    if [ ! -f "$LOCAL" ]; then
        echo "❌ NOT FOUND: $FNAME"
        ((FAIL++))
        continue
    fi

    echo -n "Uploading $FNAME... "

    aws s3 cp "$LOCAL" "s3://$BUCKET/$S3KEY" \
        --content-type "image/png" \
        --cache-control "no-cache, no-store, must-revalidate" \
        --metadata-directive REPLACE \
        --quiet

    if [ $? -eq 0 ]; then
        echo "✅"
        ((SUCCESS++))
    else
        echo "❌ FAILED"
        ((FAIL++))
    fi
done

echo "========================================"
echo "DONE: $SUCCESS success, $FAIL failed"
