package com.smyongbu.voiceinput

import java.io.ByteArrayInputStream
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.fail
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class BundledModelFileTest {
    @get:Rule val directory = TemporaryFolder()
    private val content = "内置模型校验".toByteArray(Charsets.UTF_8)
    private fun digest(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes)
        .joinToString("") { "%02x".format(it) }

    @Test fun installsAndReusesVerifiedFile() {
        val target = File(directory.root, "model.bin")
        var opens = 0
        repeat(2) {
            BundledModelFile.install(target, content.size.toLong(), digest(content), {
                opens++
                ByteArrayInputStream(content)
            })
        }
        assertEquals(1, opens)
        assertEquals(String(content, Charsets.UTF_8), target.readText())
        assertFalse(File(directory.root, "model.bin.part").exists())
    }

    @Test fun corruptAssetPreservesPreviousFile() {
        val target = directory.newFile("model.bin").apply { writeText("旧模型") }
        try {
            BundledModelFile.install(target, content.size.toLong(), "0".repeat(64), { ByteArrayInputStream(content) })
            fail("损坏资源应被拒绝")
        } catch (_: IOException) {
            assertEquals("旧模型", target.readText())
        }
    }

    @Test fun shortAssetDoesNotBecomeInstalled() {
        val target = File(directory.root, "missing.bin")
        try {
            BundledModelFile.install(target, content.size.toLong() + 1, digest(content), { ByteArrayInputStream(content) })
            fail("不完整资源应被拒绝")
        } catch (_: IOException) {
            assertFalse(target.exists())
        }
    }
}
