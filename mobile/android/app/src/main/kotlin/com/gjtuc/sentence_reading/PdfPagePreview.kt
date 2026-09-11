package com.gjtuc.sentence_reading

import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import java.io.ByteArrayOutputStream
import java.io.File
import kotlin.math.max

/** design/197 — render one PDF page to PNG for figure layout edit background. */
object PdfPagePreview {
    fun renderPng(path: String, pageIndex: Int, maxSidePx: Int = 1400): ByteArray? {
        if (pageIndex < 0) return null
        val file = File(path)
        if (!file.isFile || file.length() <= 0L) return null
        if (!path.lowercase().endsWith(".pdf")) return null
        var pfd: ParcelFileDescriptor? = null
        var renderer: PdfRenderer? = null
        var page: PdfRenderer.Page? = null
        var bitmap: Bitmap? = null
        try {
            pfd = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
            renderer = PdfRenderer(pfd)
            if (pageIndex >= renderer.pageCount) return null
            page = renderer.openPage(pageIndex)
            val srcW = page.width.coerceAtLeast(1)
            val srcH = page.height.coerceAtLeast(1)
            val scale = maxSidePx.toFloat() / max(srcW, srcH).toFloat()
            val w = (srcW * scale).toInt().coerceAtLeast(1)
            val h = (srcH * scale).toInt().coerceAtLeast(1)
            // WHY: ARGB bitmap starts transparent; PdfRenderer blends onto it so
            // the page looks black and black PDF ink disappears (layout edit dark mode).
            bitmap = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
            bitmap.eraseColor(android.graphics.Color.WHITE)
            page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
            val out = ByteArrayOutputStream()
            if (!bitmap.compress(Bitmap.CompressFormat.PNG, 100, out)) return null
            val bytes = out.toByteArray()
            return if (bytes.isEmpty()) null else bytes
        } catch (_: Exception) {
            return null
        } finally {
            try { page?.close() } catch (_: Exception) {}
            try { renderer?.close() } catch (_: Exception) {}
            try { pfd?.close() } catch (_: Exception) {}
            try { bitmap?.recycle() } catch (_: Exception) {}
        }
    }
}
