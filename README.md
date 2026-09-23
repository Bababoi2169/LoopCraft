# LoopCraft — Handmade Crochet Bracelet Store

A full-stack ecommerce web application built with Python and Flask.
Designed for a small handmade business selling custom crochet bracelets.

## Features

- Browse and search products by category
- Persistent shopping cart across sessions
- Razorpay payment gateway with server-side signature verification
- Custom order form with Instagram DM integration
- Interactive delivery address selection via Leaflet.js map
- Order history with shipment tracking number support
- Full admin panel — manage products, orders, users, and stock
- Low stock alerts in admin dashboard
- CSRF protection on all state-changing routes

## Tech Stack

- **Backend** — Python 3, Flask, SQLAlchemy, SQLite
- **Frontend** — Jinja2, Vanilla CSS, Vanilla JavaScript
- **Payments** — Razorpay
- **Maps** — Leaflet.js, OpenStreetMap, Nominatim
- **Auth** — Flask-Login, Flask-Bcrypt
- **Admin** — Flask-Admin

## Setup

1. Clone the repository
   ```
   git clone https://github.com/Bababoi2169/E-Com.git
   cd E-Com
   ```

2. Create and activate a virtual environment
   ```
   python -m venv .venv

   # Windows
   .venv\Scripts\activate

   # macOS / Linux
   source .venv/bin/activate
   ```

3. Install dependencies
   ```
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the root directory
   ```
   SECRET_KEY=your-secret-key-here
   RAZORPAY_KEY_ID=your-razorpay-key-id
   RAZORPAY_KEY_SECRET=your-razorpay-key-secret
   ```
   Generate a quick local `SECRET_KEY` with:
   ```
   python -c "import secrets; print(secrets.token_hex(16))"
   ```
   For Razorpay test keys, sign up at razorpay.com and go to
   Settings → API Keys → Generate Test Keys.

5. Run the app
   ```
   python app.py
   ```
   On first run this creates `ecommerce.db` automatically and seeds 6 demo
   products — no separate migration step needed.

6. Visit `http://localhost:5000`

## Notes

- The first registered account is automatically granted admin access
- Admin panel is accessible at `/admin`
- Product images are stored as URLs — use Imgur or Cloudinary to host images
- Razorpay is in test mode by default — use test card `4208 5288 8888 8881` to try payments
- By default the app runs with `debug=False`. To enable Flask's debug mode locally, set `FLASK_DEBUG=1` in your `.env` — never enable this in production

## Author

Ayushmaan Agrahari
