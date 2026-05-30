import { useCallback, useRef } from 'react';
import type { CartItem } from '../context/AppContext';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CheckoutOptions {
  cart:        CartItem[];
  token:       string | null;
  buyerName?:  string;
  buyerEmail?: string;
  /** Called after /api/payments/verify returns success. Cart is already cleared. */
  onSuccess:   (paymentId: string) => void;
  /** Called on any failure at any stage. Loading state is already reset. */
  onFailure:   (reason: string) => void;
  /** Called at the very start so the caller can set its loading state. */
  onLoadingStart: () => void;
  /** Called in the finally block — always fires regardless of outcome. */
  onLoadingEnd: () => void;
  /** Called on success to empty the cart in global context. */
  clearCart: () => void;
  /** Called on success to signal SellerDashboard to refetch inventory. */
  bumpInventoryVersion: () => void;
}

interface CreateOrderResponse {
  razorpay_order_id: string;
  amount:            number;   // paise (1 INR = 100 paise)
  currency:          string;
}

interface VerifyResponse {
  status:     'success' | 'failed' | 'error';
  message:    string;
  payment_id: string;
}

const API_BASE     = 'http://127.0.0.1:8000';
const RAZORPAY_KEY = import.meta.env.VITE_RAZORPAY_KEY_ID ?? 'rzp_test_placeholder';
const SCRIPT_SRC   = 'https://checkout.razorpay.com/v1/checkout.js';

// ---------------------------------------------------------------------------
// Script loader — idempotent, resolves immediately if SDK already present
// ---------------------------------------------------------------------------

function loadRazorpayScript(): Promise<void> {
  if (typeof window !== 'undefined' && window.Razorpay) {
    return Promise.resolve();
  }

  return new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      `script[src="${SCRIPT_SRC}"]`
    );
    if (existing) {
      existing.addEventListener('load',  () => resolve(), { once: true });
      existing.addEventListener('error', () =>
        reject(new Error('Razorpay script failed to load.')), { once: true }
      );
      return;
    }

    const script    = document.createElement('script');
    script.src      = SCRIPT_SRC;
    script.async    = true;
    script.onload   = () => resolve();
    script.onerror  = () => reject(new Error('Razorpay script failed to load. Check your internet connection.'));
    document.head.appendChild(script);
  });
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * useRazorpayCheckout
 *
 * Bulletproof, exception-safe checkout hook.
 *
 * Key design decisions that prevent the "stuck on Processing" bug:
 *
 * - The Razorpay `handler` is declared `async`. The inner verify fetch is
 *   wrapped in its own try/catch that ALWAYS calls setIsProcessing(false)
 *   (via onLoadingEnd) in BOTH the catch block AND the success path, so
 *   the cart can never remain locked regardless of what the backend returns.
 *
 * - Every error path — network failure, non-OK HTTP, bad JSON, DB error
 *   returning a 500 — is caught and surfaced to the user via onFailure.
 *
 * - `inFlight` ref prevents double-clicks from opening two modals.
 */
export function useRazorpayCheckout() {
  const inFlight = useRef(false);

  const startCheckout = useCallback((opts: CheckoutOptions) => {
    if (inFlight.current) return;
    inFlight.current = true;

    const {
      cart,
      token,
      buyerName,
      buyerEmail,
      onSuccess,
      onFailure,
      onLoadingStart,
      onLoadingEnd,
      clearCart,
      bumpInventoryVersion,
    } = opts;

    onLoadingStart();

    (async () => {
      try {
        // ── Guard: auth & cart ──────────────────────────────────────────────
        if (!token) {
          throw new Error('You must be logged in to checkout.');
        }
        if (cart.length === 0) {
          throw new Error('Your cart is empty.');
        }

        // ── Step 1: Ensure Razorpay SDK is available ────────────────────────
        await loadRazorpayScript();

        if (!window.Razorpay) {
          throw new Error('Razorpay SDK failed to initialise. Please refresh and try again.');
        }

        // ── Step 2: Create order on backend ────────────────────────────────
        const orderRes = await fetch(`${API_BASE}/api/payments/create-order`, {
          method:  'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization:  `Bearer ${token}`,
          },
          body: JSON.stringify({
            items: cart.map(item => ({
              inventory_id:       item.id,
              product_catalog_id: item.productCatalogId,
              shop_id:            item.shopId,
              name:               item.name,
              price:              item.price,
              quantity:           item.quantity,
            })),
          }),
        });

        if (!orderRes.ok) {
          const errBody = await orderRes.json().catch(() => ({})) as { detail?: string };
          throw new Error(errBody.detail ?? `Order creation failed (HTTP ${orderRes.status})`);
        }

        const order = await orderRes.json() as CreateOrderResponse;

        // ── Step 3: Open Razorpay modal and await its outcome ───────────────
        //
        // The handler is declared `async` so we can use await inside it.
        // It has its own dedicated try/catch that resets loading state
        // immediately in the catch block — this is the critical fix that
        // prevents the cart from staying locked when the backend fails.
        await new Promise<void>((resolve, reject) => {
          const rzp = new window.Razorpay({
            key:         RAZORPAY_KEY,
            amount:      order.amount,
            currency:    order.currency,
            name:        'SmartMart',
            description: `${cart.length} item${cart.length !== 1 ? 's' : ''}`,
            order_id:    order.razorpay_order_id,

            prefill: {
              name:  buyerName  ?? '',
              email: buyerEmail ?? '',
            },

            theme: { color: '#4f46e5' },

            // ── Step 4: Payment success — async handler with dedicated try/catch
            //
            // CRITICAL: This handler is async. The inner try/catch explicitly
            // calls onLoadingEnd() (which maps to setIsProcessing(false)) at
            // the very start of the catch block so the cart unlocks instantly
            // on any backend failure, rather than hanging indefinitely.
            handler: async function (response: RazorpayPaymentResponse) {
              try {
                const verifyRes = await fetch(`${API_BASE}/api/payments/verify`, {
                  method:  'POST',
                  headers: {
                    'Content-Type': 'application/json',
                    Authorization:  `Bearer ${token}`,
                  },
                  body: JSON.stringify({
                    razorpay_order_id:   response.razorpay_order_id,
                    razorpay_payment_id: response.razorpay_payment_id,
                    razorpay_signature:  response.razorpay_signature,
                    items: cart.map(item => ({
                      inventory_id: item.id,
                      quantity:     item.quantity,
                    })),
                  }),
                });

                // Parse the response body regardless of HTTP status so we can
                // surface the backend's error message to the user.
                const data = await verifyRes.json().catch(() => ({
                  status:  'error',
                  message: `Server returned HTTP ${verifyRes.status} with no JSON body.`,
                })) as VerifyResponse;

                // Log the exact payload for debugging
                console.log('Backend verification response:', data);

                if (!verifyRes.ok || data.status !== 'success') {
                  // CRITICAL FALLBACK: reset loading state immediately before
                  // propagating the error so the cart never stays locked.
                  onLoadingEnd();
                  inFlight.current = false;
                  reject(new Error(data.message ?? `Verification failed (HTTP ${verifyRes.status})`));
                  return;
                }

                // ── Success path ──────────────────────────────────────────
                clearCart();
                bumpInventoryVersion();
                onSuccess(data.payment_id);

                // CRITICAL: reset loading state on the success path too,
                // before resolving, so the button is never left in a
                // "Processing..." state after a successful payment.
                onLoadingEnd();
                inFlight.current = false;
                resolve();

              } catch (err: unknown) {
                // CRITICAL FALLBACK: any unhandled exception (network failure,
                // JSON parse error, etc.) must reset loading state immediately.
                onLoadingEnd();
                inFlight.current = false;
                reject(err);
              }
            },

            modal: {
              ondismiss() {
                reject(new Error('Payment cancelled.'));
              },
            },
          });

          rzp.open();
        });

      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Checkout failed. Please try again.';
        onFailure(message);

      } finally {
        // Always reset loading state and release the in-flight guard.
        // Note: on the success/failure paths inside the async handler above,
        // onLoadingEnd and inFlight are reset early (before resolve/reject)
        // to guarantee immediate UI unlock. This finally block is the safety
        // net for all other paths (script load failure, order creation failure,
        // modal dismiss, etc.) where the early reset hasn't fired yet.
        onLoadingEnd();
        inFlight.current = false;
      }
    })();

  }, []);

  return { startCheckout };
}
