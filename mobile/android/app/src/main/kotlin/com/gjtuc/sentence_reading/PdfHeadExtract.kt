package com.gjtuc.sentence_reading

import android.content.Context
import android.net.Uri
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.text.PDFTextStripper
import java.io.File
import java.io.FileOutputStream
import kotlin.math.min

/**
 * design/228 · 231 — head text + Info.Title from SAF content:// (no OCR).
 * Caller passes maxReadBytes (default 50MB); abort with too_large above cap.
 * Never include URI/path in returned map values used for evidence.
 */
object PdfHeadExtract {
    @Volatile
    private var inited = false

    fun ensureInit(context: Context) {
        if (!inited) {
            synchronized(this) {
                if (!inited) {
                    PDFBoxResourceLoader.init(context.applicationContext)
                    inited = true
                }
            }
        }
    }

    fun extract(
        context: Context,
        uri: Uri,
        maxChars: Int,
        maxPages: Int,
        maxReadBytes: Int,
    ): Map<String, Any?> {
        ensureInit(context)
        val t0 = System.currentTimeMillis()
        var temp: File? = null
        try {
            val resolver = context.contentResolver
            val input = resolver.openInputStream(uri)
                ?: return fail("null_stream", t0)
            temp = File.createTempFile("pdf_head_", ".pdf", context.cacheDir)
            input.use { src ->
                FileOutputStream(temp).use { dst ->
                    val buf = ByteArray(64 * 1024)
                    var total = 0
                    while (true) {
                        val n = src.read(buf)
                        if (n <= 0) break
                        total += n
                        if (total > maxReadBytes) {
                            return fail("too_large", t0)
                        }
                        dst.write(buf, 0, n)
                    }
                }
            }
            PDDocument.load(temp).use { doc ->
                val infoTitle = try {
                    doc.documentInformation?.title?.trim().orEmpty()
                } catch (_: Exception) {
                    ""
                }
                val pages = doc.numberOfPages
                val end = min(maxPages.coerceAtLeast(1), pages.coerceAtLeast(0))
                val stripper = PDFTextStripper().apply {
                    startPage = 1
                    endPage = end.coerceAtLeast(1)
                }
                var head = try {
                    if (pages <= 0) "" else stripper.getText(doc)
                } catch (_: Exception) {
                    ""
                }
                var truncated = false
                if (head.length > maxChars) {
                    head = head.substring(0, maxChars)
                    truncated = true
                }
                return mapOf(
                    "ok" to true,
                    "headText" to head,
                    "infoTitle" to infoTitle,
                    "pageCount" to pages,
                    "truncated" to truncated,
                    "elapsedMs" to (System.currentTimeMillis() - t0).toInt(),
                    "code" to "",
                )
            }
        } catch (e: SecurityException) {
            return fail("stale", t0)
        } catch (e: Exception) {
            return fail("parse_fail", t0)
        } finally {
            try {
                temp?.delete()
            } catch (_: Exception) {
            }
        }
    }

    private fun fail(code: String, t0: Long): Map<String, Any?> {
        return mapOf(
            "ok" to false,
            "headText" to "",
            "infoTitle" to "",
            "pageCount" to 0,
            "truncated" to false,
            "elapsedMs" to (System.currentTimeMillis() - t0).toInt(),
            "code" to code,
        )
    }
}
