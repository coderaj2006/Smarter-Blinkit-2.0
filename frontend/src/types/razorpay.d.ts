// ---------------------------------------------------------------------------
// Minimal ambient type declaration for the Razorpay browser SDK.
// The SDK is loaded via a <script> tag in index.html and attaches to window.
// There is no official @types/razorpay package for the browser SDK.
// ---------------------------------------------------------------------------

interface RazorpayOptions {
  key: string;
  amount: number;           // paise (1 INR = 100 paise)
  currency: string;
  name: string;
  description?: string;
  image?: string;
  order_id: string;         // razorpay_order_id from backend
  handler: (response: RazorpayPaymentResponse) => void;
  prefill?: {
    name?: string;
    email?: string;
    contact?: string;
  };
  theme?: {
    color?: string;
  };
  modal?: {
    ondismiss?: () => void;
  };
}

interface RazorpayPaymentResponse {
  razorpay_payment_id: string;
  razorpay_order_id:   string;
  razorpay_signature:  string;
}

interface RazorpayInstance {
  open(): void;
  on(event: string, handler: () => void): void;
}

interface Window {
  Razorpay: new (options: RazorpayOptions) => RazorpayInstance;
}
