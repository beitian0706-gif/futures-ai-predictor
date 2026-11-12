package com.futuresai.app;

import android.app.Activity;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import org.json.JSONObject;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private WebView web;
    private final ExecutorService executor = Executors.newFixedThreadPool(3);

    public class NetworkBridge {
        @JavascriptInterface public void request(String id, String address, String method, String body) {
            executor.execute(() -> {
                HttpURLConnection connection = null;
                try {
                    URL url = new URL(address);
                    String scheme = url.getProtocol();
                    if (!(scheme.equals("http") || scheme.equals("https"))) throw new Exception("仅支持 HTTP/HTTPS 地址");
                    if (url.getUserInfo() != null) throw new Exception("服务器地址不能包含账号密码");
                    if (!(method.equals("GET") || method.equals("POST"))) throw new Exception("不支持的请求方法");
                    connection = (HttpURLConnection) url.openConnection();
                    connection.setConnectTimeout(10000);
                    connection.setReadTimeout(20000);
                    connection.setRequestMethod(method);
                    connection.setRequestProperty("Accept", "application/json");
                    if (method.equals("POST")) {
                        connection.setDoOutput(true);
                        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                        try (OutputStream output = connection.getOutputStream()) { output.write(body.getBytes(StandardCharsets.UTF_8)); }
                    }
                    int status = connection.getResponseCode();
                    InputStream stream = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
                    String response = stream == null ? "" : new String(stream.readAllBytes(), StandardCharsets.UTF_8);
                    if (stream != null) stream.close();
                    if (status >= 400) {
                        String detail = "HTTP " + status;
                        try { detail = new JSONObject(response).optString("detail", detail); } catch (Exception ignored) {}
                        deliver(id, false, detail);
                    } else deliver(id, true, response);
                } catch (Exception error) { deliver(id, false, error.getMessage() == null ? "网络连接失败" : error.getMessage()); }
                finally { if (connection != null) connection.disconnect(); }
            });
        }
    }

    private void deliver(String id, boolean ok, String result) {
        String script = "window.__nativeResult(" + JSONObject.quote(id) + "," + ok + "," + JSONObject.quote(result) + ")";
        runOnUiThread(() -> { if (web != null) web.evaluateJavascript(script, null); });
    }

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        web = new WebView(this);
        web.setWebViewClient(new WebViewClient());
        web.setWebChromeClient(new WebChromeClient());
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        web.addJavascriptInterface(new NetworkBridge(), "FuturesNative");
        web.loadUrl("file:///android_asset/index.html");
        setContentView(web);
    }
    @Override public void onBackPressed() { if (web.canGoBack()) web.goBack(); else super.onBackPressed(); }
    @Override protected void onDestroy() { executor.shutdownNow(); if (web != null) { web.destroy(); web = null; } super.onDestroy(); }
}
