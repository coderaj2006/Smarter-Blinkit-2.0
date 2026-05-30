import React, { useEffect, useRef, useState } from 'react';
import { Html5Qrcode, Html5QrcodeSupportedFormats } from 'html5-qrcode';
import { Camera, X, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { useAppContext } from '../context/AppContext';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ScanResult {
  barcode:        string;
  productName:    string | null;
  newStockCount:  number;
}

interface BarcodeScannerProps {
  /** Called when the modal should close. */
  onClose: () => void;
}

const API_BASE = 'http://127.0.0.1:8000';
const SCANNER_ELEMENT_ID = 'barcode-scanner-region';

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const BarcodeScanner: React.FC<BarcodeScannerProps> = ({ onClose }) => {
  const { token } = useAppContext();

  const scannerRef  = useRef<Html5Qrcode | null>(null);
  const isScanning  = useRef(false);   // guard against double-scan callbacks

  const [status,     setStatus]     = useState<'idle' | 'scanning' | 'updating' | 'success' | 'error'>('idle');
  const [lastResult, setLastResult] = useState<ScanResult | null>(null);
  const [errorMsg,   setErrorMsg]   = useState<string | null>(null);

  // -------------------------------------------------------------------------
  // Start camera on mount, stop on unmount
  // -------------------------------------------------------------------------
  useEffect(() => {
    const scanner = new Html5Qrcode(SCANNER_ELEMENT_ID, { verbose: false });
    scannerRef.current = scanner;

    scanner
      .start(
        { facingMode: 'environment' },   // rear camera on mobile
        {
          fps: 10,
          qrbox: { width: 260, height: 160 },
          formatsToSupport: [
            Html5QrcodeSupportedFormats.EAN_13,
            Html5QrcodeSupportedFormats.EAN_8,
            Html5QrcodeSupportedFormats.CODE_128,
            Html5QrcodeSupportedFormats.CODE_39,
            Html5QrcodeSupportedFormats.UPC_A,
            Html5QrcodeSupportedFormats.UPC_E,
            Html5QrcodeSupportedFormats.QR_CODE,
          ],
        },
        onScanSuccess,
        () => { /* ignore per-frame decode errors */ }
      )
      .then(() => setStatus('scanning'))
      .catch(err => {
        setStatus('error');
        setErrorMsg(
          err instanceof Error
            ? err.message
            : 'Camera access denied. Please allow camera permissions and try again.'
        );
      });

    return () => {
      scanner.isScanning && scanner.stop().catch(() => {});
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // -------------------------------------------------------------------------
  // Scan success callback — fires on every decoded frame
  // -------------------------------------------------------------------------
  const onScanSuccess = async (barcode: string) => {
    // Debounce: ignore subsequent frames until the PATCH resolves
    if (isScanning.current) return;
    isScanning.current = true;

    // Pause the scanner visually while we call the API
    setStatus('updating');

    try {
      const res = await fetch(`${API_BASE}/api/inventory/update-by-barcode`, {
        method:  'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization:  `Bearer ${token}`,
        },
        body: JSON.stringify({ barcode }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Server error ${res.status}`);
      }

      const data: { barcode: string; product_name: string; new_stock_quantity: number } =
        await res.json();

      setLastResult({
        barcode:       data.barcode,
        productName:   data.product_name,
        newStockCount: data.new_stock_quantity,
      });
      setStatus('success');

      // Resume scanning after 2 s so the seller can scan the next item
      setTimeout(() => {
        isScanning.current = false;
        setStatus('scanning');
        setLastResult(null);
      }, 2000);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Update failed.');
      setStatus('error');
      isScanning.current = false;
    }
  };

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Barcode scanner"
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Camera className="w-5 h-5 text-primary-600" />
            <h2 className="font-semibold text-gray-900">Scan Product Barcode</h2>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="Close scanner"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Camera viewport */}
        <div className="relative bg-black">
          {/* html5-qrcode mounts the <video> element inside this div */}
          <div id={SCANNER_ELEMENT_ID} className="w-full" style={{ minHeight: 240 }} />

          {/* Overlay states */}
          {status === 'updating' && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/60 gap-2">
              <Loader2 className="w-8 h-8 text-white animate-spin" />
              <p className="text-white text-sm font-medium">Updating stock…</p>
            </div>
          )}

          {status === 'success' && lastResult && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-green-900/80 gap-2 px-4 text-center">
              <CheckCircle className="w-10 h-10 text-green-300" />
              <p className="text-white font-semibold text-sm">
                {lastResult.productName ?? lastResult.barcode}
              </p>
              <p className="text-green-200 text-xs">
                Stock updated → {lastResult.newStockCount} units
              </p>
            </div>
          )}
        </div>

        {/* Status bar */}
        <div className="px-5 py-3 bg-gray-50 border-t border-gray-100 min-h-[52px] flex items-center gap-2">
          {status === 'idle' && (
            <p className="text-xs text-gray-500">Initialising camera…</p>
          )}
          {status === 'scanning' && (
            <>
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              <p className="text-xs text-gray-600">
                Point the camera at a product barcode to increment its stock by 1.
              </p>
            </>
          )}
          {status === 'error' && (
            <>
              <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
              <p className="text-xs text-red-600">{errorMsg}</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
