"""
Deal alert system.

Compares active listings against sold medians and absolute thresholds.
Sends email when deals trigger configured rules.
"""

import json
import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def evaluate_alerts(prices_data: dict, config: dict) -> list[dict]:
    """
    Evaluate all alert rules against current price data.

    Returns list of triggered alerts, each a dict with:
      - rule_name, set_id, set_name, product, title, price, threshold_detail, url
    """
    alerts_config = config.get("alerts", {})
    if not alerts_config.get("enabled", False):
        return []

    rules = alerts_config.get("rules", [])
    triggered = []

    tcg = prices_data.get("tcgplayer", {})
    ebay = prices_data.get("ebay", {})

    for set_id, ebay_data in ebay.items():
        set_name = set_id.replace("-", " ").title()

        for rule in rules:
            if rule["product"] == "booster_pack":
                bp = ebay_data.get("booster_pack", {})
                sold = bp.get("sold", {})
                active = bp.get("active_listings", [])
                median = sold.get("median_price_usd")

                for listing in active:
                    price = listing.get("price_usd")
                    if price is None:
                        continue

                    if rule["type"] == "pct_below_median" and median and median > 0:
                        pct_below = ((median - price) / median) * 100
                        if pct_below >= rule["threshold_pct"]:
                            triggered.append({
                                "rule_name": rule["name"],
                                "set_id": set_id,
                                "set_name": set_name,
                                "product": "booster_pack",
                                "title": listing.get("title", ""),
                                "price_usd": price,
                                "threshold_detail": f"{pct_below:.0f}% below median (${median})",
                                "url": listing.get("url", ""),
                            })

                    elif rule["type"] == "absolute_floor":
                        if price <= rule["threshold_usd"]:
                            triggered.append({
                                "rule_name": rule["name"],
                                "set_id": set_id,
                                "set_name": set_name,
                                "product": "booster_pack",
                                "title": listing.get("title", ""),
                                "price_usd": price,
                                "threshold_detail": f"Under ${rule['threshold_usd']} floor",
                                "url": listing.get("url", ""),
                            })

            elif rule["product"] == "chase_single":
                singles = ebay_data.get("chase_singles", {})
                for card_name, card_data in singles.items():
                    sold = card_data.get("sold", {})
                    active = card_data.get("active_listings", [])
                    median = sold.get("median_price_usd")

                    for listing in active:
                        price = listing.get("price_usd")
                        if price is None:
                            continue

                        if rule["type"] == "pct_below_median" and median and median > 0:
                            pct_below = ((median - price) / median) * 100
                            if pct_below >= rule["threshold_pct"]:
                                triggered.append({
                                    "rule_name": rule["name"],
                                    "set_id": set_id,
                                    "set_name": set_name,
                                    "product": f"chase_single: {card_name}",
                                    "title": listing.get("title", ""),
                                    "price_usd": price,
                                    "threshold_detail": f"{pct_below:.0f}% below median (${median})",
                                    "url": listing.get("url", ""),
                                })

    # Also check GameNerdz, Amazon, Pokemon Center listings against absolute floor
    for source_name, source_key in [("GameNerdz", "gamenerdz"), ("Amazon", "amazon"), ("Pokemon Center", "pokemoncenter")]:
        source_data = prices_data.get(source_key, {})
        for set_id, set_products in source_data.items():
            if set_id.startswith("_"):
                continue
            set_name = set_id.replace("-", " ").title()
            for rule in rules:
                if rule["product"] != "booster_pack":
                    continue
                if isinstance(set_products, list):
                    products = set_products  # Flat list (Pokemon Center format)
                elif isinstance(set_products, dict):
                    products = set_products.get("booster-pack", [])
                else:
                    continue
                if not isinstance(products, list):
                    continue
                for item in products:
                    price = item.get("price_usd")
                    if price is None:
                        continue
                    # Skip out-of-stock for Pokemon Center
                    if source_key == "pokemoncenter" and not item.get("in_stock", True):
                        continue

                    if rule["type"] == "absolute_floor" and price <= rule.get("threshold_usd", 0):
                        triggered.append({
                            "rule_name": rule["name"],
                            "set_id": set_id,
                            "set_name": set_name,
                            "product": f"booster_pack ({source_name})",
                            "title": item.get("title", ""),
                            "price_usd": price,
                            "threshold_detail": f"Under ${rule['threshold_usd']} floor ({source_name})",
                            "url": item.get("url", ""),
                        })

    # Check GameNerdz Deal of the Day (always alert on these)
    gn_dotd = prices_data.get("gamenerdz", {}).get("_deal_of_day", [])
    for item in gn_dotd:
        if item.get("price_usd"):
            triggered.append({
                "rule_name": "gamenerdz_dotd",
                "set_id": "various",
                "set_name": "GameNerdz DOTD",
                "product": "deal_of_day",
                "title": item.get("title", ""),
                "price_usd": item["price_usd"],
                "threshold_detail": f"Deal of the Day{' (was $' + str(item['original_price_usd']) + ')' if item.get('original_price_usd') else ''}",
                "url": item.get("url", ""),
            })

    # Check Reddit top deals (high-upvote posts = community-validated deals)
    reddit_top = prices_data.get("reddit", {}).get("top_deals", [])
    for deal in reddit_top[:5]:  # Top 5 highest-voted
        if deal.get("score", 0) >= 50:
            triggered.append({
                "rule_name": "reddit_hot_deal",
                "set_id": ", ".join(deal.get("matched_sets", [])) or "various",
                "set_name": deal.get("source_store", "Reddit"),
                "product": "community_deal",
                "title": deal.get("title", "")[:100],
                "price_usd": deal.get("price_mentioned", 0) or 0,
                "threshold_detail": f"Reddit hot deal ({deal.get('score', 0)} upvotes, {deal.get('num_comments', 0)} comments)",
                "url": deal.get("reddit_url", deal.get("url", "")),
            })

    # Pokemon Center restocks (MSRP buys on high-demand sets)
    pc_data = prices_data.get("pokemoncenter", {})
    for set_id, items in pc_data.items():
        if not isinstance(items, list):
            continue
        set_name = set_id.replace("-", " ").title()
        for item in items:
            if item.get("in_stock"):
                triggered.append({
                    "rule_name": "pokemoncenter_restock",
                    "set_id": set_id,
                    "set_name": set_name,
                    "product": "restock",
                    "title": item.get("title", ""),
                    "price_usd": item.get("price_usd", 0) or 0,
                    "threshold_detail": f"RESTOCK at Pokemon Center{' ($' + str(item['price_usd']) + ')' if item.get('price_usd') else ''}",
                    "url": item.get("url", ""),
                })

    log.info(f"Alert evaluation complete: {len(triggered)} deals triggered")
    return triggered


def format_email_html(alerts: list[dict]) -> str:
    """Format triggered alerts into an HTML email body."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    rows = ""
    for a in alerts:
        url = a.get("url", "#")
        rows += f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #eee;">{a['set_name']}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">{a['product']}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;font-weight:bold;color:#1a7a2e;">${a['price_usd']:.2f}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">{a['threshold_detail']}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">
                <a href="{url}" style="color:#2563eb;">View &rarr;</a>
            </td>
        </tr>"""

    return f"""
    <html>
    <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:700px;margin:0 auto;padding:20px;">
        <h2 style="color:#1e293b;">Pokemon TCG Pack Finder — Deal Alert</h2>
        <p style="color:#64748b;">Found {len(alerts)} deal(s) as of {now}</p>
        <table style="width:100%;border-collapse:collapse;font-size:14px;">
            <thead>
                <tr style="background:#f8fafc;">
                    <th style="padding:8px;text-align:left;">Set</th>
                    <th style="padding:8px;text-align:left;">Product</th>
                    <th style="padding:8px;text-align:left;">Price</th>
                    <th style="padding:8px;text-align:left;">Why</th>
                    <th style="padding:8px;text-align:left;">Link</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
        <p style="color:#94a3b8;font-size:12px;margin-top:20px;">
            Prices are volatile. This is not financial advice. Verify listings before purchasing.
        </p>
    </body>
    </html>
    """


def send_alert_email(alerts: list[dict], config: dict) -> bool:
    """Send deal alert email via SMTP. Returns True on success."""
    email_cfg = config.get("alerts", {}).get("email", {})

    smtp_host = email_cfg.get("smtp_host", "smtp.gmail.com")
    smtp_port = email_cfg.get("smtp_port", 587)
    use_tls = email_cfg.get("use_tls", True)
    smtp_user = os.environ.get(email_cfg.get("from_env", "ALERT_SMTP_USER"), "")
    smtp_pass = os.environ.get(email_cfg.get("password_env", "ALERT_SMTP_PASS"), "")
    recipient = os.environ.get(email_cfg.get("recipient_env", "ALERT_EMAIL_TO"), "")

    if not all([smtp_user, smtp_pass, recipient]):
        log.warning("Email credentials not configured — skipping alert email")
        log.warning("Set ALERT_SMTP_USER, ALERT_SMTP_PASS, and ALERT_EMAIL_TO env vars")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"TCG Pack Finder: {len(alerts)} deal(s) found"
    msg["From"] = smtp_user
    msg["To"] = recipient

    html_body = format_email_html(alerts)
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if use_tls:
                server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        log.info(f"Alert email sent to {recipient}")
        return True
    except Exception as e:
        log.error(f"Failed to send alert email: {e}")
        return False


def run(prices_json_path: str = "data/prices.json", config_path: str = "config.json"):
    """Entry point — evaluate alerts and send email if any triggered."""
    with open(prices_json_path, "r", encoding="utf-8") as f:
        prices = json.load(f)
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    alerts = evaluate_alerts(prices, config)

    if alerts:
        log.info(f"\n{'='*60}")
        log.info(f"DEALS FOUND: {len(alerts)}")
        for a in alerts:
            log.info(f"  [{a['set_name']}] {a['product']} — ${a['price_usd']:.2f} ({a['threshold_detail']})")
            log.info(f"    {a['url']}")
        log.info(f"{'='*60}\n")

        send_alert_email(alerts, config)
    else:
        log.info("No deals triggered current alert rules.")

    return alerts
