import os
import time
import json
import logging
import base64
import base58
from typing import Dict, Any, Optional
from dotenv import load_dotenv

from eth_account import Account
from eth_account.messages import encode_defunct

# StandX libraries
from perp_http import StandXPerpHTTP
from perps_auth import StandXAuth, Chain

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("StandXBot")

# Load environment variables
load_dotenv()

PRIVATE_KEY_HEX = os.getenv("WALLET_PRIVATE_KEY")
API_BASE_URL = os.getenv("STANDX_API_URL", "https://perps.standx.com")
GEO_API_URL = os.getenv("STANDX_GEO_URL", "https://geo.standx.com")

def get_signer(private_key_hex: str):
    """
    Creates a signer function compatible with StandXAuth.
    """
    # Remove '0x' prefix if present
    if private_key_hex.startswith("0x"):
        private_key_hex = private_key_hex[2:]
    
    account = Account.from_key(private_key_hex)
    
    def sign_message(message: str) -> str:
        # StandX requires signing the message directly (sometimes needs EIP-191, sometimes raw).
        # Based on docs/examples usually it is standard personal_sign (EIP-191) for EVM.
        # The auth module passes the message string.
        msg_encoded = encode_defunct(text=message)
        signed = account.sign_message(msg_encoded)
        return "0x" + signed.signature.hex()
        
    return account.address, sign_message

def check_connection():
    """
    Attempts to authenticate and query user balance to verify connection.
    Does NOT execute any trades.
    """
    if not PRIVATE_KEY_HEX:
        logger.error("WALLET_PRIVATE_KEY not found in .env file")
        return

    try:
        logger.info("Initializing StandX Client...")
        client = StandXPerpHTTP(base_url=API_BASE_URL, geo_url=GEO_API_URL)
        
        # 1. Health Check - SKIPPED (User reported 404)
        # logger.info("Checking API Health...")
        # health = client.health_check()
        # logger.info(f"Health Check: {health}")
        
        # 2. Authentication
        logger.info("Authenticating...")
        
        # StandXAuth expects Ed25519 key for request signing, BUT the initial login 
        # is done via wallet signature (EVM/Solana).
        # We need to instantiate StandXAuth. If we don't pass a key, it generates a new ephemeral one.
        # This ephemeral key is used to sign API requests AFTER login.
        auth = StandXAuth() 
        
        address, sign_func = get_signer(PRIVATE_KEY_HEX)
        logger.info(f"Wallet Address: {address}")
        
        # Perform Login
        # Chain is 'bsc' as per user request
        login_resp = auth.authenticate(chain="bsc", wallet_address=address, sign_message=sign_func)
        logger.info(f"Login successful! Token: {login_resp.token[:10]}...")
        
        # 3. Query Balance
        logger.info("Querying Balance...")
        balance = client.query_balance(token=login_resp.token)
        
        logger.info("-" * 30)
        logger.info("ACCOUNT BALANCE:")
        logger.info(json.dumps(balance, indent=2))
        logger.info("-" * 30)
        
        # 4. Check Open Orders (Just to see)
        logger.info("Querying Open Orders...")
        open_orders = client.query_open_orders(token=login_resp.token, symbol="BTC-DUSD")
        logger.info(f"Open Orders: {open_orders.get('total', 0)}")
        
        logger.info("CONNECTION VERIFICATION COMPLETED SUCCESSFULLY.")
        
    except Exception as e:
        logger.error(f"An error occurred during verification: {e}")
        import traceback
        traceback.print_exc()

# --- CONFIGURATION TRADING ---
SYMBOL = "BTC-DUSD"
SPREAD_BPS = 8          # 8 bps = 0.08% (Target < 10 bps)
ORDER_SIZE = "0.0015"    # BTC Size (Adjust based on your balance!)
REFRESH_RATE = 30       # Seconds between updates

# Additional Env Vars for Mode 2
API_TOKEN = os.getenv("STANDX_API_TOKEN")
API_KEY = os.getenv("STANDX_API_KEY")


def get_auth_context_private_key():
    """Authenticates using Wallet Private Key (Mode 1)"""
    if not PRIVATE_KEY_HEX:
        logger.error("Error: WALLET_PRIVATE_KEY is missing in .env for Mode 1.")
        return None
    
    logger.info("[Mode 1] Authenticating with Private Key...")
    client = StandXPerpHTTP(base_url=API_BASE_URL, geo_url=GEO_API_URL)
    
    # Generate ephemeral key for this session
    auth = StandXAuth()
    
    address, sign_func = get_signer(PRIVATE_KEY_HEX)
    logger.info(f"Wallet Address: {address}")
    
    try:
        login_resp = auth.authenticate(chain="bsc", wallet_address=address, sign_message=sign_func)
        logger.info("Login successful.")
        return {
            "client": client,
            "auth": auth,
            "token": login_resp.token,
            "address": address
        }
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        return None



def get_auth_context_api_token():
    """Uses provided API Token and Sign Key (Mode 2)"""
    if not API_TOKEN or not API_KEY:
        logger.error("Error: STANDX_API_TOKEN or STANDX_API_KEY is missing in .env for Mode 2.")
        return None

    logger.info("[Mode 2] using API Token (Keyless)...")
    client = StandXPerpHTTP(base_url=API_BASE_URL, geo_url=GEO_API_URL)

    # Initialize Auth with the PERSISTENT signing key
    try:
        raw_key = API_KEY.strip()
        private_key_bytes = None

        # Try 1: Hex
        try:
            k = raw_key
            if k.startswith("0x"): k = k[2:]
            private_key_bytes = bytes.fromhex(k)
        except ValueError:
            pass
        
        # Try 2: Base64
        if not private_key_bytes or len(private_key_bytes) != 32:
            try:
                private_key_bytes = base64.b64decode(raw_key)
            except Exception:
                pass

        # Try 3: Base58
        if not private_key_bytes or len(private_key_bytes) != 32:
            try:
                private_key_bytes = base58.b58decode(raw_key)
            except Exception:
                pass
        
        # Check result
        if not private_key_bytes or len(private_key_bytes) != 32:
            raise ValueError(f"Could not decode API Key to 32 bytes (Length: {len(private_key_bytes) if private_key_bytes else 0}). Check format (Hex, Base64, or Base58).")

        auth = StandXAuth(private_key=private_key_bytes)
        logger.info("Signing key loaded successfully.")
    except Exception as e:
        logger.error(f"Failed to load Signing Key: {e}")
        return None

    return {
        "client": client,
        "auth": auth,
        "token": API_TOKEN,
        "address": "API_TOKEN_USER"
    }

def run_trading_bot():
    """
    Main Market Making Loop for StandX Uptime Program
    Rules:
    - Maintain Bid AND Ask orders
    - Within 10 bps of Mark Price (target 8 bps)
    - Refresh orders regularly
    """
    
    print("\n--- STANDX TRADING BOT ---")
    print("Select Authentication Mode:")
    print("1. Private Key Wallet (requires WALLET_PRIVATE_KEY) : rabby, metamask, etc.")
    print("2. Keyless Wallet (requires STANDX_API_TOKEN & STANDX_API_KEY) : Binance wallet")
    
    choice = input("Enter choice (1 or 2): ").strip()
    
    context = None
    if choice == "1":
        context = get_auth_context_private_key()
    elif choice == "2":
        context = get_auth_context_api_token()
    else:
        print("Invalid choice. Exiting.")
        return

    if not context:
        logger.error("Failed to initialize context. Exiting.")
        return

    client = context['client']
    auth = context['auth']
    token = context['token']
    user_label = context['address']
    
    # 1. Determine Symbol from Env
    env_symbol = os.getenv("SYMBOL", "BTC").upper()
    # Normalize: If user put "BTC", make it "BTC-USD".
    # Even if margined in DUSD, the pair name on StandX is "BTC-USD".
    if not env_symbol.endswith("-USD"):
        current_symbol = f"{env_symbol}-USD"
    else:
        current_symbol = env_symbol
        
    # Prompt for Order Size
    default_size = ORDER_SIZE
    size_input = input(f"Enter Order Size for {current_symbol} [Default: {default_size}]: ").strip()
    
    if not size_input:
        current_order_size = default_size
    else:
        current_order_size = size_input

    logger.info(f"Starting Bot on {current_symbol} for user {user_label}...")
    logger.info(f"Spread Target: {SPREAD_BPS} bps | Size: {current_order_size} {current_symbol.split('-')[0]}")
    
    try:
        while True:
            try:
                # 1. Get Mark Price
                price_data = client.query_symbol_price(current_symbol)
                mark_price = float(price_data['mark_price'])
                
                # 2. Calculate Bid/Ask Prices
                # "within 10 bps of the spread" usually means distance from Mark/Mid.
                # StandX docs: "within 10 bps of the spread" -> likely means (Price - Mark) / Mark <= 0.0010
                # We stick to +/- 8 bps from Mark Price.
                
                spread_factor = SPREAD_BPS / 10000.0  # 8 / 10000 = 0.0008
                bid_price = mark_price * (1 - spread_factor)
                ask_price = mark_price * (1 + spread_factor)
                
                # Format prices to appropriate precision (StandX usually needs string)
                # Assuming 1 tick size (adjust if needed, usually 0.1 or 1 for BTC)
                # Format prices to appropriate precision (StandX usually needs string)
                # Assuming 1 tick size (adjust if needed, usually 0.1 or 1 for BTC)
                # WARNING: Integers might not work for low value coins.
                # We should probably use 2 decimals or dynamic precision.
                # For safety/simplicity let's try to detect if price is small.
                if mark_price < 100:
                    # Use 4 decimals for small prices
                    bid_price_str = f"{bid_price:.4f}"
                    ask_price_str = f"{ask_price:.4f}"
                else:
                    # Use integer for large prices (like BTC) or 2 decimals
                    # Safer to use valid tick size, but without metadata we guess.
                    # Start with 2 decimals for generic, or int for very high?
                    # Original code used int() which is bad for ETH/SOL.
                    # Let's upgrade to 2 decimals default, or keep int for BTC specifically?
                    # The user specifically asked for "DDUSD". If DUSD is ~1$, int() will break spread (0 or 1).
                    bid_price_str = f"{bid_price:.2f}"
                    ask_price_str = f"{ask_price:.2f}"
                
                logger.info(f"Mark: {mark_price:.4f} | Target Bid: {bid_price_str} | Target Ask: {ask_price_str}")

                # 3. Cancel Open Orders for this symbol
                try:
                    open_orders = client.query_open_orders(token, symbol=current_symbol)
                    result_list = open_orders.get('result', [])
                    total_open = len(result_list)
                    
                    if total_open > 0:
                        logger.info(f"Found {total_open} open orders. Cancelling...")
                        # Log shows key is 'id', not 'order_id'
                        ids_to_cancel = [o['id'] for o in result_list]
                        
                        if ids_to_cancel:
                            # Try batch cancel first
                            try:
                                client.cancel_orders(token, order_id_list=ids_to_cancel, auth=auth)
                                logger.info(f"SUCCESS: Cancelled {len(ids_to_cancel)} orders (Batch).")
                            except Exception as batch_error:
                                logger.warning(f"Batch cancel failed ({batch_error}). Retrying one by one...")
                                # Fallback: one by one
                                for oid in ids_to_cancel:
                                    try:
                                        client.cancel_orders(token, order_id_list=[oid], auth=auth)
                                        logger.info(f"Cancelled order {oid}")
                                    except Exception as single_error:
                                        logger.error(f"FAILED to cancel order {oid}: {single_error}")

                except Exception as e:
                    logger.error(f"CRITICAL ERROR in Cancel Orders step: {e}")

                # 4. Check & Auto-Close Positions (Delta Neutrality)
                try:
                    positions = client.query_positions(token, symbol=current_symbol)
                    # logger.info(f"Debug Positions: {positions}") # Uncomment if needed
                    
                    has_position = False
                    for pos in positions:
                        if pos.get('symbol') == current_symbol:
                            qty = float(pos.get('qty', 0))
                            if qty != 0:
                                has_position = True
                                logger.warning(f"!!! OPEN POSITION DETECTED: {qty} {current_symbol} !!!")
                                logger.info("Attempting CLOSE via Market Order...")
                                
                                close_side = "sell" if qty > 0 else "buy"
                                try:
                                    client.place_order(
                                        token=token,
                                        symbol=current_symbol,
                                        side=close_side,
                                        order_type="market",
                                        qty=str(abs(qty)),
                                        time_in_force="ioc",
                                        reduce_only=True,
                                        auth=auth,
                                        price=None
                                    )
                                    logger.info(">>> POSITION CLOSE ORDER SENT <<<")
                                except Exception as close_error:
                                    logger.error(f"FAILED to update position close order: {close_error}")
                    
                    if not has_position:
                        # Optional: Log if clean
                        # logger.info("No open positions. Clean.")
                        pass

                except Exception as e:
                    logger.error(f"CRITICAL ERROR in Position Check step: {e}")

                # 5. Place New Orders
                # Buy Order
                client.place_order(
                    token=token,
                    symbol=current_symbol,
                    side="buy",
                    order_type="limit",
                    qty=current_order_size,
                    price=bid_price_str,
                    time_in_force="gtc",
                    reduce_only=False,
                    auth=auth
                )
                
                # Sell Order
                client.place_order(
                    token=token,
                    symbol=current_symbol,
                    side="sell",
                    order_type="limit",
                    qty=current_order_size,
                    price=ask_price_str,
                    time_in_force="gtc",
                    reduce_only=False,
                    auth=auth
                )
                
                logger.info("Orders placed successfully.")
                
                # 6. Wait
                time.sleep(REFRESH_RATE)

            except Exception as loop_error:
                logger.error(f"Error in trading loop: {loop_error}")
                time.sleep(5) # Wait a bit before retrying

    except KeyboardInterrupt:
        logger.info("Bot stopped by user. Cleaning up...")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        logger.info("Emergency exit. Cleaning up...")
    finally:
        # ATTEMPT TO CANCEL ALL OPEN ORDERS ON STOP
        if context and client and token:
            try:
                logger.info("SHUTDOWN SEQUENCE: Cancelling all open orders...")
                open_orders = client.query_open_orders(token, symbol=current_symbol)
                result_list = open_orders.get('result', [])
                if result_list:
                    ids_to_cancel = [o['id'] for o in result_list]
                    logger.info(f"Retrieved {len(ids_to_cancel)} open orders to cancel.")
                    # Try batch cancel
                    try:
                        client.cancel_orders(token, order_id_list=ids_to_cancel, auth=auth)
                        logger.info(f"Shutdown: Cancelled {len(ids_to_cancel)} orders.")
                    except Exception as batch_error:
                         # Fallback one by one
                        for oid in ids_to_cancel:
                            try:
                                client.cancel_orders(token, order_id_list=[oid], auth=auth)
                            except:
                                pass
                        logger.info("Shutdown: Cancelled orders via fallback.")
                else:
                    logger.info("Shutdown: No open orders found.")
            except Exception as cleanup_error:
                logger.error(f"Failed to cleanup orders on exit: {cleanup_error}")

if __name__ == "__main__":
    # Uncomment the function you want to run
    # check_connection()
    run_trading_bot()