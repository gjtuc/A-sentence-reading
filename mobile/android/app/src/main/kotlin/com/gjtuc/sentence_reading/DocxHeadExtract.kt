package com.gjtuc.sentence_reading

import android.content.Context
import android.net.Uri
import android.util.Xml
import org.xmlpull.v1.XmlPullParser
import java.io.InputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream

/**
 * design/254 — head text + infoTitle from DOCX (OpenXML ZIP).
 * Parses word/document.xml (<w:p>, <w:t>) and docProps/core.xml (<dc:title>).
 * Pure streaming, no external dependencies, fast and lightweight.
 */
object DocxHeadExtract {
    fun extract(
        context: Context,
        uri: Uri,
        maxChars: Int = 8000,
        maxParagraphs: Int = 40,
        maxReadBytes: Int = 50 * 1024 * 1024,
    ): Map<String, Any?> {
        val t0 = System.currentTimeMillis()
        var infoTitle = ""
        val headBuilder = StringBuilder()
        var paragraphCount = 0
        var truncated = false

        try {
            val input = context.contentResolver.openInputStream(uri)
                ?: return fail("null_stream", t0)

            input.use { rawIn ->
                val zip = ZipInputStream(rawIn)
                var entry: ZipEntry? = zip.nextEntry
                var foundCore = false
                var foundDoc = false

                while (entry != null) {
                    val name = entry.name
                    if (!foundCore && (name == "docProps/core.xml" || name.endsWith("/core.xml"))) {
                        infoTitle = parseCoreTitle(zip)
                        foundCore = true
                    } else if (!foundDoc && (name == "word/document.xml" || name.endsWith("/document.xml"))) {
                        val (text, isTrunc) = parseDocumentXml(zip, maxChars, maxParagraphs)
                        headBuilder.append(text)
                        truncated = isTrunc
                        foundDoc = true
                    }
                    if (foundCore && foundDoc) break
                    zip.closeEntry()
                    entry = zip.nextEntry
                }
            }

            val head = headBuilder.toString().trim()
            return mapOf(
                "ok" to true,
                "headText" to head,
                "infoTitle" to infoTitle.trim(),
                "pageCount" to 1,
                "truncated" to truncated,
                "elapsedMs" to (System.currentTimeMillis() - t0).toInt(),
            )
        } catch (e: Exception) {
            return fail(e.message ?: "extract_fail", t0)
        }
    }

    private fun parseCoreTitle(input: InputStream): String {
        return try {
            val parser = Xml.newPullParser()
            parser.setFeature(XmlPullParser.FEATURE_PROCESS_NAMESPACES, false)
            parser.setInput(input, "UTF-8")
            var eventType = parser.eventType
            var inTitle = false
            var title = ""

            while (eventType != XmlPullParser.END_DOCUMENT) {
                when (eventType) {
                    XmlPullParser.START_TAG -> {
                        val name = parser.name
                        if (name.equals("dc:title", ignoreCase = true) || name.equals("title", ignoreCase = true)) {
                            inTitle = true
                        }
                    }
                    XmlPullParser.TEXT -> {
                        if (inTitle) {
                            title = parser.text?.trim().orEmpty()
                        }
                    }
                    XmlPullParser.END_TAG -> {
                        val name = parser.name
                        if (name.equals("dc:title", ignoreCase = true) || name.equals("title", ignoreCase = true)) {
                            inTitle = false
                            if (title.isNotEmpty()) return title
                        }
                    }
                }
                eventType = parser.next()
            }
            title
        } catch (_: Exception) {
            ""
        }
    }

    private fun parseDocumentXml(
        input: InputStream,
        maxChars: Int,
        maxParagraphs: Int,
    ): Pair<String, Boolean> {
        val sb = StringBuilder()
        var paragraphCount = 0
        var truncated = false

        try {
            val parser = Xml.newPullParser()
            parser.setFeature(XmlPullParser.FEATURE_PROCESS_NAMESPACES, false)
            parser.setInput(input, "UTF-8")
            var eventType = parser.eventType
            var inParagraph = false
            var inText = false
            val currentP = StringBuilder()

            while (eventType != XmlPullParser.END_DOCUMENT) {
                when (eventType) {
                    XmlPullParser.START_TAG -> {
                        val name = parser.name
                        if (name.equals("w:p", ignoreCase = true) || name.equals("p", ignoreCase = true)) {
                            inParagraph = true
                            currentP.setLength(0)
                        } else if (name.equals("w:t", ignoreCase = true) || name.equals("t", ignoreCase = true)) {
                            inText = true
                        }
                    }
                    XmlPullParser.TEXT -> {
                        if (inParagraph && inText) {
                            val t = parser.text
                            if (t != null) currentP.append(t)
                        }
                    }
                    XmlPullParser.END_TAG -> {
                        val name = parser.name
                        if (name.equals("w:t", ignoreCase = true) || name.equals("t", ignoreCase = true)) {
                            inText = false
                        } else if (name.equals("w:p", ignoreCase = true) || name.equals("p", ignoreCase = true)) {
                            inParagraph = false
                            val pText = currentP.toString().trim()
                            if (pText.isNotEmpty()) {
                                if (sb.isNotEmpty()) sb.append("\n")
                                sb.append(pText)
                                paragraphCount++
                                if (sb.length >= maxChars || paragraphCount >= maxParagraphs) {
                                    truncated = sb.length >= maxChars
                                    return Pair(
                                        if (sb.length > maxChars) sb.substring(0, maxChars) else sb.toString(),
                                        truncated,
                                    )
                                }
                            }
                        }
                    }
                }
                eventType = parser.next()
            }
        } catch (_: Exception) {
            // End of stream or XML parse abort on partial read
        }
        return Pair(
            if (sb.length > maxChars) sb.substring(0, maxChars) else sb.toString(),
            truncated,
        )
    }

    private fun fail(reason: String, t0: Long): Map<String, Any?> = mapOf(
        "ok" to false,
        "reason" to reason,
        "headText" to "",
        "infoTitle" to "",
        "pageCount" to 0,
        "truncated" to false,
        "elapsedMs" to (System.currentTimeMillis() - t0).toInt(),
    )
}
