from pathlib import Path
import re

root = Path(__file__).resolve().parent
app = root / "app"
gradle = app / "build.gradle"
text = gradle.read_text(encoding="utf-8")
text = text.replace("versionCode 4; versionName '0.4.0'", "versionCode 5; versionName '0.4.1'")
gradle.write_text(text, encoding="utf-8")

html = app / "src/main/assets/index.html"
text = html.read_text(encoding="utf-8")
text = text.replace('<input id="server" placeholder="例如 http://192.168.1.20:8000"/>', '<input id="server" value="http://110.42.130.206" readonly/>')
text = text.replace('分析服务器地址（手机可访问的局域网IP或HTTPS地址）', '云端分析服务器（已自动配置）')
text = text.replace('</script></body></html>', 'window.addEventListener("load",connect);\n</script></body></html>')
html.write_text(text, encoding="utf-8")

java = app / "src/main/java/com/futuresai/app/MainActivity.java"
text = java.read_text(encoding="utf-8")
text = text.replace('import android.webkit.WebSettings;', 'import android.webkit.WebSettings;\nimport java.io.InputStream;\nimport java.nio.charset.StandardCharsets;')
old = 'web.loadUrl("file:///android_asset/index.html");'
new = '''try (InputStream in = getAssets().open("index.html")) {
            byte[] bytes = in.readAllBytes();
            String page = new String(bytes, StandardCharsets.UTF_8);
            web.loadDataWithBaseURL("http://110.42.130.206/", page, "text/html", "UTF-8", null);
        } catch (Exception e) {
            web.loadData("<h3>界面加载失败</h3>", "text/html", "UTF-8");
        }'''
if old not in text: raise RuntimeError("Expected original MainActivity not found")
java.write_text(text.replace(old,new), encoding="utf-8")
print("V0.4.1 patch applied")
