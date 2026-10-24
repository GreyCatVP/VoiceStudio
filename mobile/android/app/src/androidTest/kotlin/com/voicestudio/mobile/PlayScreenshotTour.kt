package com.voicestudio.mobile

import android.graphics.Bitmap
import android.os.ParcelFileDescriptor
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.voicestudio.mobile.l10n.L10n
import com.voicestudio.mobile.local.ModelCatalog
import com.voicestudio.mobile.local.PhoneRuntime
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TestRule
import org.junit.runner.Description
import org.junit.runner.RunWith
import org.junit.runners.model.Statement
import java.io.File
import java.util.Locale

/**
 * Provisions the smallest speech model in the app's own model store before the
 * activity starts, so the tour shows a phone that already has it. Skips the
 * whole test (before launch) unless `playScreenshots=true`; downloads only with
 * the same explicit flags as LocalInferenceTest.
 */
class SmallestSpeechModel: TestRule {
    override fun apply(base: Statement, description: Description): Statement = object: Statement() {
        override fun evaluate() {
            val args=InstrumentationRegistry.getArguments()
            assumeTrue("Pass playScreenshots=true to capture the Play screenshots",args.getString("playScreenshots")=="true")
            val context=InstrumentationRegistry.getInstrumentation().targetContext
            val tts=context.assets.open("models.json").bufferedReader().use {ModelCatalog.decode(it.readText())}.models.filter {it.capability=="tts"}.minBy {it.totalBytes}
            val runtime=PhoneRuntime.get(context)
            assertTrue("Use a device with the declared model RAM",tts.fits(runtime.ramBytes))
            if(tts.gated&&!runtime.licence.accepted(tts)) {
                assertEquals("Pass acceptModelLicencesForSmoke=true only after reviewing the bundled terms","true",args.getString("acceptModelLicencesForSmoke"))
                runtime.licence.record(tts,true)
            }
            if(args.getString("downloadSmokeModels")=="true"&&!runtime.downloads.installed(tts)) runBlocking {runtime.downloads.download(tts,true)}
            assertTrue("Explicitly provision the smallest speech model first",runtime.downloads.installed(tts))
            base.evaluate()
        }
    }
}

/**
 * Google Play phone screenshots from the real debug app, phone-first (no paired
 * computer). The mobile workflow's `android-screenshots` job runs it on a 16:9
 * emulator, pulls the PNGs and uploads them as the `android-play-screenshots` artifact.
 */
@RunWith(AndroidJUnit4::class)
class PlayScreenshotTour {
    @get:Rule(order=0) val model=SmallestSpeechModel()
    @get:Rule(order=1) val compose=createAndroidComposeRule<MainActivity>()
    private val instrumentation get()=InstrumentationRegistry.getInstrumentation()
    private val l by lazy {L10n.load(instrumentation.targetContext,"en")}
    private val shots by lazy {File(checkNotNull(instrumentation.targetContext.getExternalFilesDir(null)),"play-screenshots")}

    @Test fun capturePlayStoreScreenshots() {
        assertEquals("Run the tour with the device in English","en",Locale.getDefault().language)
        shots.deleteRecursively();shots.mkdirs()
        statusBarDemo(true)
        try {
            val home=hasTestTag("home.speak")
            val no=hasText(l.t("consent.no")) and hasClickAction()
            compose.waitUntil(30_000) {exists(home)}
            compose.waitForIdle()
            if(exists(no)) compose.onNode(no).performClick()
            compose.waitUntil(10_000) {!exists(hasText(l.t("consent.no")))}
            shot("01-home")

            compose.onNodeWithTag("home.speak").performScrollTo().performClick()
            val editor=hasText(l.t("mobile.speak.placeholder"))
            // Generate replaces the download card only once the provisioned model is installed and accepted.
            val generate=hasText(l.t("mobile.speak.generate")) and hasClickAction()
            compose.waitUntil(30_000) {exists(editor)&&exists(generate)}
            compose.onNode(editor).performTextInput("Welcome to VoiceStudio. This voice was generated right here on the phone.")
            compose.onNode(generate).performScrollTo().performClick()
            val share=hasText(l.t("mobile.speak.share")) and hasClickAction()
            compose.waitUntil(180_000) {exists(share)&&!exists(hasText(l.t("common.cancel")))}
            compose.onNode(hasText(l.t("mobile.tabs.speak")) and isHeading()).performScrollTo()
            shot("02-speak")

            tab("mobile.tabs.voices");shot("03-voices")
            tab("mobile.tabs.dub");shot("04-dub")
            tab("mobile.tabs.dictate");shot("05-dictate")
            tab("mobile.tabs.settings");shot("07-settings")

            compose.onNodeWithText(l.t("mobile.local.models")).performScrollTo().performClick()
            val delete=hasText(l.t("common.delete")) and hasClickAction()
            compose.waitUntil(30_000) {exists(hasText(l.t("mobile.local.models")) and isHeading())&&exists(delete)}
            // Only installed models offer Delete: bring the downloaded one into view.
            compose.onNode(delete).performScrollTo()
            shot("06-models")
        } finally {statusBarDemo(false)}
    }

    private fun exists(matcher: SemanticsMatcher)=compose.onAllNodes(matcher).fetchSemanticsNodes().isNotEmpty()

    private fun tab(key: String) {
        compose.onNode(hasText(l.t(key)) and SemanticsMatcher.expectValue(SemanticsProperties.Role,Role.Tab)).performClick()
        compose.waitUntil(15_000) {exists(hasText(l.t(key)) and isHeading())}
    }

    /** Whole display, status and navigation bars included, checked against Play's phone screenshot rules. */
    private fun shot(name: String) {
        compose.waitForIdle()
        runCatching {instrumentation.uiAutomation.waitForIdle(500,5_000)}
        val bitmap=checkNotNull(instrumentation.uiAutomation.takeScreenshot()) {"No screenshot for $name"}
        val long=maxOf(bitmap.width,bitmap.height)
        val short=minOf(bitmap.width,bitmap.height)
        assertTrue("$name is ${bitmap.width}x${bitmap.height}: Play needs the long side at most twice the short side; use a 16:9 device",long<=2*short)
        assertTrue("$name is ${bitmap.width}x${bitmap.height}: Play needs 320 to 3840 px per side",short>=320&&long<=3840)
        File(shots,"$name.png").outputStream().use {assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG,100,it))}
        bitmap.recycle()
    }

    private fun shell(command: String) {
        ParcelFileDescriptor.AutoCloseInputStream(instrumentation.uiAutomation.executeShellCommand(command)).use {it.readBytes()}
    }

    /** SystemUI demo mode: a fixed clock, full battery and signal, no notification icons. */
    private fun statusBarDemo(on: Boolean) {
        val demo="am broadcast -a com.android.systemui.demo -e command"
        if(!on) {shell("$demo exit");return}
        shell("settings put global sysui_demo_allowed 1")
        listOf("enter","clock -e hhmm 0941","battery -e level 100 -e plugged false","network -e wifi show -e level 4",
            "network -e mobile show -e datatype none -e level 4","notifications -e visible false").forEach {shell("$demo $it")}
    }
}
