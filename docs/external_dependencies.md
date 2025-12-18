

## **EXTERNAL DEPENDENCIES & ACCOUNT TRANSITION CHECKLIST**

This section documents external services required to operate the Prospector, for engineering/product team ownership transition.

---

### 1\. Firebase (Authentication & Analytics)

| Attribute | Value |
| :---- | :---- |
| **Project ID** | `prospector-leaderl-board` |
| **Console URL** | [https://console.firebase.google.com/project/prospector-leaderl-board](https://console.firebase.google.com/project/prospector-leaderl-board) |
| **Services Used** | Authentication (Google Sign-In), Firestore |
| **Firestore Collections** | `users`, `building_visits`, `homepage_visits` |
| **Domain Restriction** | Only `@rzero.com` emails can sign in |
| **Pricing Tier** | Verify in console (likely Spark free or Blaze pay-as-you-go) |

**Config location**: `src/generators/homepage.py` lines 40-47

```py
'firebase_config': {
    'apiKey': 'AIzaSyAsxPRzyj7z6Nk3QPhOBK5CfyblY2LqAjk',
    'authDomain': 'prospector-leaderl-board.firebaseapp.com',
    'projectId': 'prospector-leaderl-board',
    'storageBucket': 'prospector-leaderl-board.firebasestorage.app',
    'messagingSenderId': '70489892630',
    'appId': '1:70489892630:web:51052e8b0b5da2e6779237'
}
```

**⚠️ TRANSITION ACTION REQUIRED:**

- [ ] Verify Firebase project ownership (personal vs organizational Google account)  
- [ ] Transfer project ownership to organizational account if needed  
- [ ] Add team members as project editors: Firebase Console → Settings → Users and permissions  
- [ ] Review authorized domains: Authentication → Settings → Authorized domains  
- [ ] Document Firestore security rules

---

### 2\. Mapbox (Interactive Maps)

| Attribute | Value |
| :---- | :---- |
| **Access Token** | `pk.eyJ1IjoiZm1pbGxlcnJ6ZXJvIiwiYSI6ImNtY2NnZGl6dTAxMzkya29qeHl6c2tibDgifQ...` |
| **Account Username** | `fmillerrzero` (visible in token \- likely personal) |
| **Style Used** | `mapbox://styles/mapbox/streets-v12` |
| **Pricing** | Free tier: 50,000 map loads/month; then $5/1,000 loads |

**Config location**: `src/generators/homepage.py` line 34

**⚠️ TRANSITION ACTION REQUIRED:**

- [ ] This token is tied to a personal account (`fmillerrzero`)  
- [ ] Create R-Zero organizational Mapbox account at [https://account.mapbox.com/](https://account.mapbox.com/)  
- [ ] Generate new access token with appropriate scopes  
- [ ] Update `mapbox_token` in `src/generators/homepage.py`  
- [ ] Consider URL restrictions on the token for production security

---

### 3\. Google Maps Platform (Places Autocomplete)

| Attribute | Value |
| :---- | :---- |
| **API Key** | Currently set to `REMOVED_GOOGLE_KEY` in homepage.py |
| **APIs Used** | Places API (Autocomplete for address search) |
| **Pricing** | $2.83 per 1,000 autocomplete requests (first $200/month free) |

**Config location**: `src/generators/homepage.py` line 37

**⚠️ TRANSITION ACTION REQUIRED:**

- [ ] Determine which Google Cloud project owns the production API key  
- [ ] Verify billing account association in Google Cloud Console  
- [ ] Transfer to organizational GCP project if on personal account  
- [ ] Add API key restrictions (HTTP referrer restrictions) for security  
- [ ] Update `google_api_key` in config

---

### 4\. AWS S3 (Image Hosting)

| Attribute | Value |
| :---- | :---- |
| **Bucket Name** | `nationwide-odcv-images` |
| **Region** | `us-east-2` (Ohio) |
| **Base URL** | `https://nationwide-odcv-images.s3.us-east-2.amazonaws.com` |
| **Contents** | `/logos/`, `/logo-thumbnails/`, `/images/`, `/thumbnails/` |
| **Access** | Public read (configured via bucket policy) |

**Config location**: `src/config.py` lines 106-114

**Full documentation**: `docs/AWS_S3_BUCKET.md`

**⚠️ TRANSITION ACTION REQUIRED:**

- [ ] Verify AWS account ownership (whose account is the bucket in?)  
- [ ] Ensure IAM credentials are documented and transferred  
- [ ] Add team members to AWS account with appropriate IAM roles  
- [ ] Review bucket policy (currently allows public read)  
- [ ] Estimate monthly costs (S3 storage \+ data transfer)  
- [ ] Consider setting up AWS Organization if not already

**Credentials needed for uploads**:

- AWS CLI configured with `aws configure`, or  
- Environment variables `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`

---

### 5\. SerpAPI (Logo Fetching)

| Attribute | Value |
| :---- | :---- |
| **Used By** | `scripts/logos/fetch_validate_upload_logos.py` |
| **Purpose** | Fetches organization logos via Google Image Search |
| **Pricing** | Pay per search (free tier: 100 searches/month) |

**⚠️ TRANSITION ACTION REQUIRED:**

- [ ] Verify SerpAPI account ownership  
- [ ] Check API key location (likely environment variable or hardcoded)  
- [ ] Transfer to organizational account if personal

---

### 6\. OpenAI API (Image Validation)

| Attribute | Value |
| :---- | :---- |
| **Used By** | `scripts/logos/fetch_validate_upload_logos.py`, `scripts/images/fetch_validate_upload.py` |
| **Purpose** | Vision API validates that fetched images are correct logos/buildings |
| **Pricing** | Pay per token (GPT-4 Vision) |

**⚠️ TRANSITION ACTION REQUIRED:**

- [ ] Verify OpenAI account ownership  
- [ ] Check API key location (likely `OPENAI_API_KEY` environment variable)  
- [ ] Transfer to organizational account if personal  
- [ ] Set up usage limits/alerts

---

### 7\. Google Street View API (Building Images)

| Attribute | Value |
| :---- | :---- |
| **Used By** | `scripts/images/fetch_*.py` scripts |
| **Purpose** | Fetches street view images of buildings |
| **Pricing** | $7 per 1,000 images |

**⚠️ TRANSITION ACTION REQUIRED:**

- [ ] Verify which GCP project is used  
- [ ] Check billing association  
- [ ] May share project with Google Maps Places API

---

### 8\. External Data Dependencies (NYC Data)

| Attribute | Value |
| :---- | :---- |
| **Location** | `/Users/forrestmiller/Desktop/New/data/` (hardcoded path) |
| **Used By** | NYC-specific building reports |
| **Files** | `10_year_savings_by_building.csv`, `buildings_BIG_with_emails_complete_verified.csv`, etc. |

**Config location**: `src/config.py` lines 88-103

**⚠️ TRANSITION ACTION REQUIRED:**

- [ ] These paths are hardcoded to Forrest's machine  
- [ ] Get copies of these NYC data files  
- [ ] Update paths in `src/config.py` or make them configurable  
- [ ] Document where this data comes from and how to refresh it

---

## **DEPLOYMENT & HOSTING**

**Current hosting**: Unknown \- need to document where the generated HTML is deployed.

**Generated output location**: `output/html/index.html`

The HTML file can be hosted on:

- GitHub Pages (free)  
- Netlify (free tier)  
- AWS S3 \+ CloudFront  
- Firebase Hosting (pairs with existing Firebase project)

**⚠️ TRANSITION ACTION REQUIRED:**

- [ ] Document current production hosting location  
- [ ] Document deployment process (manual upload? CI/CD?)  
- [ ] Ensure hosting account is organizational

---

## **SUMMARY: ACCOUNTS TO TRANSFER**

| Service | Account Type | Current Owner | Action |
| :---- | :---- | :---- | :---- |
| Firebase | Unknown | Unknown | Verify & transfer |
| Mapbox | Personal (`fmillerrzero`) | Forrest Miller | Create org account |
| Google Cloud (Maps API) | Unknown | Unknown | Verify & transfer |
| AWS (S3 bucket) | Unknown | Unknown | Verify & transfer |
| SerpAPI | Unknown | Unknown | Verify & transfer |
| OpenAI | Unknown | Unknown | Verify & transfer |
| Production hosting | Unknown | Unknown | Document & transfer |

---

## **ENVIRONMENT VARIABLES CHECKLIST**

These environment variables may be needed for full functionality:

```shell
# AWS (for S3 uploads)
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx

# OpenAI (for image validation)
OPENAI_API_KEY=xxx

# SerpAPI (for logo fetching)
SERPAPI_API_KEY=xxx

# Google (may be hardcoded instead)
GOOGLE_API_KEY=xxx
```

Document which are set on the developer's machine vs CI/CD vs hardcoded.

Data file Elizabeth download from CoStar

