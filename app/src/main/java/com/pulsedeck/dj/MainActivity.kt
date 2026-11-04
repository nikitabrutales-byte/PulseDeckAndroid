package com.pulsedeck.dj

import android.app.Activity
import android.content.Intent
import android.content.pm.ActivityInfo
import android.net.Uri
import android.os.Bundle
import android.provider.DocumentsContract
import android.database.Cursor
import android.util.Base64
import android.os.ParcelFileDescriptor
import java.io.FileInputStream
import java.io.FileOutputStream
import android.view.View
import android.webkit.ConsoleMessage
import android.webkit.JavascriptInterface
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject
import java.io.InputStream

class MainActivity : Activity() {
    private lateinit var webView: WebView
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null
    private val fileChooserRequestCode = 9001
    private val folderChooserRequestCode = 9002
    private val persistentLibraryRequestCode = 9003
    private var persistentLibraryTreeUri: Uri? = null
    private var selectedTreeUri: Uri? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_FULL_SENSOR
        hideSystemBars()
        selectedTreeUri = getPreferences(MODE_PRIVATE).getString("library_tree_uri", null)?.let(Uri::parse)
        persistentLibraryTreeUri = getPreferences(MODE_PRIVATE).getString("persistent_library_tree_uri", null)?.let(Uri::parse)
        webView = WebView(this)
        webView.setLayerType(View.LAYER_TYPE_HARDWARE, null)
        webView.setBackgroundColor(android.graphics.Color.rgb(16, 23, 34))
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.allowFileAccess = true
        webView.settings.allowContentAccess = true
        webView.settings.mediaPlaybackRequiresUserGesture = true
        webView.settings.builtInZoomControls = false
        webView.settings.displayZoomControls = false
        webView.settings.setSupportZoom(false)
        webView.settings.javaScriptCanOpenWindowsAutomatically = false
        webView.settings.mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
        webView.addJavascriptInterface(PulseDeckFolderBridge(), "PulseDeckAndroid")
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val url = request?.url?.toString() ?: return true
                return !url.startsWith("file:///android_asset/")
            }
        }
        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                webView: WebView?, filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?
            ): Boolean {
                this@MainActivity.fileChooserCallback?.onReceiveValue(null)
                this@MainActivity.fileChooserCallback = filePathCallback
                val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "audio/*"
                    putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                }
                return try {
                    startActivityForResult(intent, fileChooserRequestCode)
                    true
                } catch (_: Exception) {
                    this@MainActivity.fileChooserCallback?.onReceiveValue(null)
                    this@MainActivity.fileChooserCallback = null
                    Toast.makeText(this@MainActivity, "Nelze otevřít výběr hudby.", Toast.LENGTH_SHORT).show()
                    false
                }
            }
            override fun onConsoleMessage(consoleMessage: ConsoleMessage?): Boolean = true
        }
        setContentView(webView)
        hideSystemBars()
        if (savedInstanceState == null) webView.loadUrl("file:///android_asset/index.html")
        else webView.restoreState(savedInstanceState)
    }

    private inner class PulseDeckFolderBridge {
        @JavascriptInterface
        fun openPersistentLibraryPicker() {
            runOnUiThread {
                try {
                    val intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                        addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
                        addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
                        addFlags(Intent.FLAG_GRANT_PREFIX_URI_PERMISSION)
                    }
                    startActivityForResult(intent, persistentLibraryRequestCode)
                } catch (e: Exception) {
                    Toast.makeText(this@MainActivity, "Nelze vybrat složku pro trvalou knihovnu.", Toast.LENGTH_LONG).show()
                }
            }
        }

        @JavascriptInterface
        fun hasPersistentLibrary(): Boolean = persistentLibraryTreeUri != null

        @JavascriptInterface
        fun writePersistentText(relativePath: String, content: String): Boolean {
            return try {
                val uri = ensurePersistentFile(relativePath)
                contentResolver.openOutputStream(uri, "wt")?.bufferedWriter(Charsets.UTF_8)?.use { it.write(content) } ?: return false
                true
            } catch (e: Exception) {
                android.util.Log.e("PulseDeck", "Persistent text write failed: $relativePath", e)
                false
            }
        }

        @JavascriptInterface
        fun readPersistentText(relativePath: String): String {
            return try {
                val uri = findPersistentFile(relativePath) ?: return ""
                contentResolver.openInputStream(uri)?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
            } catch (e: Exception) {
                android.util.Log.e("PulseDeck", "Persistent text read failed: $relativePath", e)
                ""
            }
        }

        @JavascriptInterface
        fun writePersistentChunk(relativePath: String, offset: Long, base64: String, totalSize: Long): Boolean {
            return try {
                val uri = ensurePersistentFile(relativePath)
                val bytes = Base64.decode(base64, Base64.DEFAULT)
                val mode = if (offset <= 0L) "rwt" else "rw"
                val pfd = contentResolver.openFileDescriptor(uri, mode) ?: return false
                ParcelFileDescriptor.AutoCloseOutputStream(pfd).use { stream ->
                    val channel = stream.channel
                    channel.position(offset.coerceAtLeast(0L))
                    var buffer = java.nio.ByteBuffer.wrap(bytes)
                    while (buffer.hasRemaining()) channel.write(buffer)
                }
                true
            } catch (e: Exception) {
                android.util.Log.e("PulseDeck", "Persistent audio write failed: $relativePath", e)
                false
            }
        }

        @JavascriptInterface
        fun readPersistentChunk(relativePath: String, offset: Long, length: Int): String {
            return try {
                val uri = findPersistentFile(relativePath) ?: return ""
                val pfd = contentResolver.openFileDescriptor(uri, "r") ?: return ""
                ParcelFileDescriptor.AutoCloseInputStream(pfd).use { stream ->
                    skipFully(stream, offset.coerceAtLeast(0L))
                    val buffer = ByteArray(length.coerceIn(1, 262144))
                    var count = 0
                    while (count < buffer.size) {
                        val n = stream.read(buffer, count, buffer.size - count)
                        if (n <= 0) break
                        count += n
                    }
                    if (count == 0) "" else Base64.encodeToString(buffer.copyOf(count), Base64.NO_WRAP)
                }
            } catch (e: Exception) {
                android.util.Log.e("PulseDeck", "Persistent audio read failed: $relativePath", e)
                ""
            }
        }

        @JavascriptInterface
        fun playbackStarted() {
            try {
                val intent = Intent(this@MainActivity, PulseDeckPlaybackService::class.java)
                    .setAction(PulseDeckPlaybackService.ACTION_PLAYING)
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) startForegroundService(intent)
                else startService(intent)
            } catch (e: Exception) {
                android.util.Log.e("PulseDeck", "Could not start playback foreground service", e)
            }
        }

        @JavascriptInterface
        fun playbackStopped() {
            try {
                stopService(Intent(this@MainActivity, PulseDeckPlaybackService::class.java))
            } catch (e: Exception) {
                android.util.Log.e("PulseDeck", "Could not stop playback foreground service", e)
            }
        }

        @JavascriptInterface
        fun openFolderPicker() {
            runOnUiThread {
                try {
                    val intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                        addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
                        addFlags(Intent.FLAG_GRANT_PREFIX_URI_PERMISSION)
                    }
                    startActivityForResult(intent, folderChooserRequestCode)
                } catch (_: Exception) {
                    Toast.makeText(this@MainActivity, "Výběr složky není dostupný.", Toast.LENGTH_SHORT).show()
                }
            }
        }

        @JavascriptInterface
        fun listAudioFiles(): String {
            val tree = selectedTreeUri ?: return "[]"
            return try {
                val result = JSONArray()
                val rootId = DocumentsContract.getTreeDocumentId(tree)
                appendAudioFiles(tree, rootId, "", result, 0)
                result.toString()
            } catch (e: Exception) {
                android.util.Log.e("PulseDeck", "Folder scan failed", e)
                "[]"
            }
        }

        @JavascriptInterface
        fun readAudioFileChunk(uriString: String, offset: Long, requestedLength: Int): String {
            return try {
                val uri = Uri.parse(uriString)
                val input = contentResolver.openInputStream(uri) ?: return ""
                input.use { stream ->
                    skipFully(stream, offset.coerceAtLeast(0))
                    val buffer = ByteArray(requestedLength.coerceIn(1, 524288))
                    var count = 0
                    while (count < buffer.size) {
                        val n = stream.read(buffer, count, buffer.size - count)
                        if (n <= 0) break
                        count += n
                    }
                    if (count == 0) "" else Base64.encodeToString(buffer.copyOf(count), Base64.NO_WRAP)
                }
            } catch (e: Exception) {
                android.util.Log.e("PulseDeck", "Audio file read failed", e)
                ""
            }
        }
    }

    private fun findChildDocument(tree: Uri, parentId: String, name: String): Pair<String, Uri>? {
        val children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, parentId)
        val projection = arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID, DocumentsContract.Document.COLUMN_DISPLAY_NAME)
        contentResolver.query(children, projection, null, null, null)?.use { cursor ->
            val idCol = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_DOCUMENT_ID)
            val nameCol = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_DISPLAY_NAME)
            while (cursor.moveToNext()) {
                if (cursor.getString(nameCol) == name) {
                    val id = cursor.getString(idCol)
                    return id to DocumentsContract.buildDocumentUriUsingTree(tree, id)
                }
            }
        }
        return null
    }

    private fun ensurePersistentDirectory(relativePath: String): Pair<String, Uri> {
        val tree = persistentLibraryTreeUri ?: throw IllegalStateException("Trvalá složka není vybraná")
        var parentId = DocumentsContract.getTreeDocumentId(tree)
        var parentUri = DocumentsContract.buildDocumentUriUsingTree(tree, parentId)
        val parts = ("PulseDeck/" + relativePath).split('/').filter { it.isNotBlank() }
        for (part in parts) {
            val existing = findChildDocument(tree, parentId, part)
            if (existing != null) {
                parentId = existing.first
                parentUri = existing.second
            } else {
                val created = DocumentsContract.createDocument(contentResolver, parentUri, DocumentsContract.Document.MIME_TYPE_DIR, part)
                    ?: throw IllegalStateException("Nelze vytvořit složku $part")
                parentId = DocumentsContract.getDocumentId(created)
                parentUri = created
            }
        }
        return parentId to parentUri
    }

    private fun ensurePersistentFile(relativePath: String): Uri {
        val parts = relativePath.split('/').filter { it.isNotBlank() }
        require(parts.isNotEmpty()) { "Prázdná cesta" }
        val parentPath = parts.dropLast(1).joinToString("/")
        val parent = ensurePersistentDirectory(parentPath)
        val tree = persistentLibraryTreeUri ?: throw IllegalStateException("Trvalá složka není vybraná")
        val existing = findChildDocument(tree, parent.first, parts.last())
        if (existing != null) return existing.second
        return DocumentsContract.createDocument(contentResolver, parent.second, "application/octet-stream", parts.last())
            ?: throw IllegalStateException("Nelze vytvořit soubor ${parts.last()}")
    }

    private fun findPersistentFile(relativePath: String): Uri? {
        val tree = persistentLibraryTreeUri ?: return null
        val parts = relativePath.split('/').filter { it.isNotBlank() }
        if (parts.isEmpty()) return null
        var parentId = DocumentsContract.getTreeDocumentId(tree)
        for (part in ("PulseDeck/" + parts.dropLast(1).joinToString("/")).split('/').filter { it.isNotBlank() }) {
            val child = findChildDocument(tree, parentId, part) ?: return null
            parentId = child.first
        }
        return findChildDocument(tree, parentId, parts.last())?.second
    }

    private fun skipFully(input: InputStream, amount: Long) {
        var remaining = amount
        while (remaining > 0) {
            val skipped = input.skip(remaining)
            if (skipped > 0) remaining -= skipped
            else { if (input.read() == -1) return; remaining-- }
        }
    }

    private fun appendAudioFiles(
        treeUri: Uri, parentDocumentId: String, relativeParent: String,
        output: JSONArray, depth: Int
    ) {
        if (depth > 20 || output.length() >= 10000) return
        val childrenUri = DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, parentDocumentId)
        val projection = arrayOf(
            DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
            DocumentsContract.Document.COLUMN_SIZE,
            DocumentsContract.Document.COLUMN_LAST_MODIFIED
        )
        var cursor: Cursor? = null
        try {
            cursor = contentResolver.query(childrenUri, projection, null, null, null) ?: return
            val idCol = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_DOCUMENT_ID)
            val nameCol = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_DISPLAY_NAME)
            val mimeCol = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_MIME_TYPE)
            val sizeCol = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_SIZE)
            val modifiedCol = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_LAST_MODIFIED)
            while (cursor.moveToNext() && output.length() < 10000) {
                val documentId = cursor.getString(idCol) ?: continue
                val name = cursor.getString(nameCol) ?: continue
                val mime = cursor.getString(mimeCol) ?: ""
                val relativePath = if (relativeParent.isEmpty()) name else "$relativeParent/$name"
                if (mime == DocumentsContract.Document.MIME_TYPE_DIR) {
                    appendAudioFiles(treeUri, documentId, relativePath, output, depth + 1)
                } else if (isAudioFile(name, mime)) {
                    val fileUri = DocumentsContract.buildDocumentUriUsingTree(treeUri, documentId)
                    val item = JSONObject()
                    item.put("name", name)
                    item.put("relativePath", relativePath)
                    item.put("uri", fileUri.toString())
                    item.put("type", mime.takeIf { it.startsWith("audio/") } ?: "audio/mpeg")
                    item.put("size", if (sizeCol >= 0 && !cursor.isNull(sizeCol)) cursor.getLong(sizeCol) else 0L)
                    item.put("lastModified", if (modifiedCol >= 0 && !cursor.isNull(modifiedCol)) cursor.getLong(modifiedCol) else System.currentTimeMillis())
                    output.put(item)
                }
            }
        } finally { cursor?.close() }
    }

    private fun isAudioFile(name: String, mime: String): Boolean {
        if (mime.startsWith("audio/")) return true
        return name.substringAfterLast('.', "").lowercase() in
            setOf("mp3", "wav", "flac", "ogg", "m4a", "aac", "opus", "aiff", "wma")
    }

    private fun hideSystemBars() {
        @Suppress("DEPRECATION")
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or View.SYSTEM_UI_FLAG_FULLSCREEN or
                View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_LAYOUT_STABLE or
                View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
        )
    }
    override fun onWindowFocusChanged(hasFocus: Boolean) { super.onWindowFocusChanged(hasFocus); if (hasFocus) hideSystemBars() }
    override fun onResume() { super.onResume(); if (::webView.isInitialized) hideSystemBars() }

    @Deprecated("Deprecated for broad device compatibility")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == fileChooserRequestCode) {
            val callback = fileChooserCallback ?: return
            val result = if (resultCode == RESULT_OK) {
                data?.clipData?.let { clip -> Array(clip.itemCount) { index -> clip.getItemAt(index).uri } }
                    ?: data?.data?.let { arrayOf(it) }
            } else null
            callback.onReceiveValue(result)
            fileChooserCallback = null
        } else if (requestCode == folderChooserRequestCode && resultCode == RESULT_OK) {
            val tree = data?.data ?: return
            val flags = data.flags and (Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            try { contentResolver.takePersistableUriPermission(tree, flags) } catch (_: Exception) {}
            selectedTreeUri = tree
            getPreferences(MODE_PRIVATE).edit().putString("library_tree_uri", tree.toString()).apply()
            webView.post { webView.evaluateJavascript("window.onNativeFolderPicked && window.onNativeFolderPicked()", null) }
        } else if (requestCode == persistentLibraryRequestCode && resultCode == RESULT_OK) {
            val tree = data?.data ?: return
            val flags = data.flags and (Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            try { contentResolver.takePersistableUriPermission(tree, flags) } catch (e: Exception) {
                android.util.Log.e("PulseDeck", "Cannot persist library folder permission", e)
            }
            persistentLibraryTreeUri = tree
            getPreferences(MODE_PRIVATE).edit().putString("persistent_library_tree_uri", tree.toString()).apply()
            try {
                listOf("Library/Tracks", "Analysis", "Playlists", "Mix Projects", "Recordings", "Library Backup").forEach {
                    ensurePersistentDirectory(it)
                }
                webView.post { webView.evaluateJavascript("window.onPersistentLibraryReady && window.onPersistentLibraryReady()", null) }
            } catch (e: Exception) {
                android.util.Log.e("PulseDeck", "Cannot initialize PulseDeck folder", e)
                Toast.makeText(this, "Složku PulseDeck se nepodařilo připravit.", Toast.LENGTH_LONG).show()
            }
        }
    }

    override fun onSaveInstanceState(outState: Bundle) { webView.saveState(outState); super.onSaveInstanceState(outState) }
    override fun onDestroy() {
        fileChooserCallback?.onReceiveValue(null)
        fileChooserCallback = null
        if (::webView.isInitialized) {
            webView.stopLoading()
            webView.loadUrl("about:blank")
            webView.removeJavascriptInterface("PulseDeckAndroid")
            webView.destroy()
        }
        super.onDestroy()
    }
}
