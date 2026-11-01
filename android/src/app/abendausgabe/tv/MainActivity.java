package app.abendausgabe.tv;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.view.KeyEvent;
import android.view.WindowManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;

/**
 * Dünne Hülle für Android TV (docs/decisions.md Nr. 18).
 *
 * <p>Zeigt die TV-Seite der Abendausgabe im Vollbild. Die Fernbedienungstasten gehen an die
 * Seite, nur „Zurück“ und „Menü“ öffnen das App-Menü. Die Server-Adresse lässt sich per adb
 * setzen ({@code --es url ...}) oder im Menü eingeben.
 */
public class MainActivity extends Activity {

    static final String PREFS = "abendausgabe";
    static final String KEY_URL = "server_url";
    static final String EXTRA_URL = "url";
    static final int NIGHT = Color.rgb(15, 28, 46);

    private WebView web;
    private AlertDialog dialog;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        web = new WebView(this);
        web.setBackgroundColor(NIGHT);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        // Videos dürfen mit Ton automatisch starten (im TV-Browser ginge das nur stumm).
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUserAgentString(settings.getUserAgentString() + " AbendausgabeTV/0.1");
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    showError(String.valueOf(error.getDescription()));
                }
            }
        });
        setContentView(web);

        if (!applyUrlFromIntent(getIntent())) {
            String url = savedUrl();
            if (url == null) {
                askForUrl();
            } else {
                web.loadUrl(url);
            }
        }
        web.requestFocus();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        applyUrlFromIntent(intent);
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
    }

    @Override
    protected void onPause() {
        web.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        if (dialog != null) {
            dialog.dismiss();
        }
        web.destroy();
        super.onDestroy();
    }

    /** „Zurück“ und „Menü“ öffnen das App-Menü; alle anderen Tasten gehen an die Seite. */
    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        int code = event.getKeyCode();
        if (code == KeyEvent.KEYCODE_BACK || code == KeyEvent.KEYCODE_MENU) {
            if (event.getAction() == KeyEvent.ACTION_UP) {
                if (code == KeyEvent.KEYCODE_BACK && web.canGoBack()) {
                    web.goBack();
                } else {
                    showMenu();
                }
            }
            return true;
        }
        return super.dispatchKeyEvent(event);
    }

    // ------------------------------------------------------------------ Adresse

    private String savedUrl() {
        return getSharedPreferences(PREFS, MODE_PRIVATE).getString(KEY_URL, null);
    }

    private void saveAndLoad(String raw) {
        String url = normalize(raw);
        if (url == null) {
            askForUrl();
            return;
        }
        SharedPreferences.Editor editor = getSharedPreferences(PREFS, MODE_PRIVATE).edit();
        editor.putString(KEY_URL, url);
        editor.apply();
        web.loadUrl(url);
    }

    private boolean applyUrlFromIntent(Intent intent) {
        if (intent == null) {
            return false;
        }
        String url = intent.getStringExtra(EXTRA_URL);
        if (url == null || url.trim().isEmpty()) {
            return false;
        }
        saveAndLoad(url);
        return true;
    }

    /** Ergänzt http:// und den Pfad /tv/, wenn nur Host und Port angegeben sind. */
    static String normalize(String raw) {
        if (raw == null) {
            return null;
        }
        String value = raw.trim();
        if (value.isEmpty()) {
            return null;
        }
        if (!value.startsWith("http://") && !value.startsWith("https://")) {
            value = "http://" + value;
        }
        Uri uri = Uri.parse(value);
        if (uri.getHost() == null || uri.getHost().isEmpty()) {
            return null;
        }
        String path = uri.getPath();
        if (path == null || path.isEmpty() || path.equals("/")) {
            value = value.replaceAll("/+$", "") + "/tv/";
        }
        return value;
    }

    /** Lädt die gespeicherte Adresse neu; nach einem Fehler hilft reload() nicht. */
    private void reloadSaved() {
        String url = savedUrl();
        if (url == null) {
            askForUrl();
        } else {
            web.loadUrl(url);
        }
    }

    // ------------------------------------------------------------------- Dialoge

    private void replaceDialog(AlertDialog next) {
        if (dialog != null && dialog.isShowing()) {
            dialog.dismiss();
        }
        dialog = next;
        dialog.show();
    }

    private void askForUrl() {
        final EditText input = new EditText(this);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        input.setSingleLine(true);
        String current = savedUrl();
        input.setText(current != null ? current : "http://");
        input.setSelection(input.getText().length());
        replaceDialog(new AlertDialog.Builder(this)
                .setTitle("Server-Adresse")
                .setMessage("Zum Beispiel 192.168.178.20:8470")
                .setView(input)
                .setPositiveButton("Speichern", (d, w) -> saveAndLoad(input.getText().toString()))
                .setNegativeButton("Abbrechen", null)
                .create());
    }

    private void showMenu() {
        String[] items = {"Weiter schauen", "Neu laden", "Server-Adresse ändern", "App beenden"};
        replaceDialog(new AlertDialog.Builder(this)
                .setTitle("Abendausgabe")
                .setItems(items, (d, which) -> {
                    if (which == 1) {
                        reloadSaved();
                    } else if (which == 2) {
                        askForUrl();
                    } else if (which == 3) {
                        finish();
                    }
                })
                .create());
    }

    private void showError(String description) {
        String url = savedUrl();
        replaceDialog(new AlertDialog.Builder(this)
                .setTitle("Server nicht erreichbar")
                .setMessage((url != null ? url : "Keine Adresse") + "\n\n" + description
                        + "\n\nLäuft der Server? Stimmt die Adresse?")
                .setPositiveButton("Erneut versuchen", (d, w) -> reloadSaved())
                .setNegativeButton("Adresse ändern", (d, w) -> askForUrl())
                .create());
    }
}
