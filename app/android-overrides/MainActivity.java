package io.github.adrijas7274.wheatcheck;

import android.os.Build;
import android.os.Bundle;
import android.webkit.ServiceWorkerClient;
import android.webkit.ServiceWorkerController;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import com.getcapacitor.BridgeActivity;

/**
 * Capacitor serves the app from https://localhost inside the APK but does not answer requests made by a service
 * worker. This routes them to the same local server, so the app's service worker can run; it adds the
 * cross-origin isolation headers that WebAssembly threads need (see app/web/sw.js).
 */
public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            ServiceWorkerController.getInstance().setServiceWorkerClient(new ServiceWorkerClient() {
                @Override
                public WebResourceResponse shouldInterceptRequest(WebResourceRequest request) {
                    return getBridge().getLocalServer().shouldInterceptRequest(request);
                }
            });
        }
    }
}
