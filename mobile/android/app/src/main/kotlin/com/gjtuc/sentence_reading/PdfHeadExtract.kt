package com.gjtuc.sentence_reading

import android.content.Context
import android.net.Uri
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.font.PDFont
import com.tom_roush.pdfbox.pdmodel.font.PDFontDescriptor
import com.tom_roush.pdfbox.text.PDFTextStripper
import com.tom_roush.pdfbox.text.TextPosition
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import kotlin.math.abs
import kotlin.math.min

/**
 * design/228 · 231 · 277 — head text + Info.Title + styled head lines (font size/bold/y).
 * Never include URI/path in returned map values used for evidence.
 */
object PdfHeadExtract {
    @Volatile
    private var inited = false

    private const val MAX_STYLE_LINES = 80
    private const val Y_LINE_TOL = 2.2f

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
                val stripper = StyledHeadStripper().apply {
                    startPage = 1
                    endPage = end.coerceAtLeast(1)
                    sortByPosition = true
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
                val headLines = ArrayList<Map<String, Any?>>(stripper.styledLines.size)
                for (line in stripper.styledLines.take(MAX_STYLE_LINES)) {
                    var t = line.text
                    if (t.length > 500) t = t.substring(0, 500)
                    headLines.add(
                        mapOf(
                            "text" to t,
                            "size_pt" to line.sizePt.toDouble(),
                            "bold" to if (line.bold) 1 else 0,
                            "y" to line.y.toDouble(),
                            "mixed_size" to if (line.mixedSize) 1 else 0,
                            "width" to line.width.toDouble(),
                        ),
                    )
                }
                return mapOf(
                    "ok" to true,
                    "headText" to head,
                    "infoTitle" to infoTitle,
                    "pageCount" to pages,
                    "truncated" to truncated,
                    "elapsedMs" to (System.currentTimeMillis() - t0).toInt(),
                    "code" to "",
                    // design/277
                    "headLines" to headLines,
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
            "headLines" to emptyList<Map<String, Any?>>(),
        )
    }

    private data class StyledLine(
        val text: String,
        val sizePt: Float,
        val bold: Boolean,
        val y: Float,
        val mixedSize: Boolean,
        val width: Float,
    )

    /**
     * design/277 — cluster TextPositions into visual lines; keep sub/sup in-line.
     */
    private class StyledHeadStripper : PDFTextStripper() {
        val styledLines = mutableListOf<StyledLine>()

        private val lineBuf = StringBuilder()
        private val sizes = mutableListOf<Float>()
        private val bolds = mutableListOf<Boolean>()
        private var lineY = Float.NaN
        private var lineX0 = Float.POSITIVE_INFINITY
        private var lineX1 = Float.NEGATIVE_INFINITY

        override fun writeString(text: String, textPositions: MutableList<TextPosition>) {
            if (textPositions.isNotEmpty()) {
                val y = textPositions.map { it.y }.average().toFloat()
                if (!lineY.isNaN() && abs(y - lineY) > Y_LINE_TOL) {
                    flushLine()
                }
                lineY = if (lineY.isNaN()) y else (lineY * 0.7f + y * 0.3f)
                lineBuf.append(text)
                for (tp in textPositions) {
                    val sz = try {
                        tp.fontSizeInPt
                    } catch (_: Exception) {
                        tp.fontSize
                    }
                    if (sz > 0.5f) sizes.add(sz)
                    bolds.add(isBoldFont(tp.font))
                    val x = tp.x
                    val right = x + tp.width
                    if (x < lineX0) lineX0 = x
                    if (right > lineX1) lineX1 = right
                }
            }
            // headText comes from getText(); skipping super drops the words.
            super.writeString(text, textPositions)
        }

        @Throws(IOException::class)
        override fun writeWordSeparator() {
            if (lineBuf.isNotEmpty()) {
                lineBuf.append(getWordSeparator())
            }
            super.writeWordSeparator()
        }

        override fun writeLineSeparator() {
            flushLine()
            super.writeLineSeparator()
        }

        override fun writeParagraphEnd() {
            flushLine()
            super.writeParagraphEnd()
        }

        override fun writePageEnd() {
            flushLine()
            super.writePageEnd()
        }

        private fun flushLine() {
            val t = lineBuf.toString().replace(Regex("\\s+"), " ").trim()
            if (t.isNotEmpty() && sizes.isNotEmpty()) {
                val sorted = sizes.sorted()
                val median = sorted[sorted.size / 2]
                val minSz = sorted.first()
                val maxSz = sorted.last()
                val mixed = maxSz > 0.5f && (maxSz - minSz) / maxSz > 0.18f
                val boldN = bolds.count { it }
                val width = if (lineX1 > lineX0) lineX1 - lineX0 else 0f
                styledLines.add(
                    StyledLine(
                        text = t,
                        sizePt = median,
                        bold = boldN * 2 >= bolds.size,
                        y = lineY,
                        mixedSize = mixed,
                        width = width,
                    ),
                )
            }
            lineBuf.setLength(0)
            sizes.clear()
            bolds.clear()
            lineY = Float.NaN
            lineX0 = Float.POSITIVE_INFINITY
            lineX1 = Float.NEGATIVE_INFINITY
        }

        private fun isBoldFont(font: PDFont?): Boolean {
            if (font == null) return false
            return try {
                val name = font.name.orEmpty()
                if (name.contains("Bold", ignoreCase = true) ||
                    name.contains("Black", ignoreCase = true) ||
                    name.contains("Heavy", ignoreCase = true)
                ) {
                    return true
                }
                val desc: PDFontDescriptor? = font.fontDescriptor
                if (desc != null) {
                    if (desc.isForceBold) return true
                    if (desc.fontWeight >= 600f) return true
                }
                false
            } catch (_: Exception) {
                false
            }
        }
    }
}
