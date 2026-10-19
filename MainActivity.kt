package com.example

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.LocalOverscrollConfiguration
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import com.example.data.model.VideoItem
import com.example.ui.player.EvaVideoPlayer
import com.example.ui.screens.FavoritesScreen
import com.example.ui.screens.FileTransferScreen
import com.example.ui.screens.FolderDetailScreen
import com.example.ui.screens.HiddenVideosScreen
import com.example.ui.screens.HomeScreen
import com.example.ui.screens.MusicScreen
import com.example.ui.screens.PlaylistsScreen
import com.example.ui.screens.PrivacySettingsScreen
import com.example.ui.screens.StorageScreen
import com.example.ui.screens.SubtitleSettingsScreen
import com.example.ui.screens.UrlStreamScreen
import com.example.ui.theme.EvaPlayerTheme
import com.example.ui.components.VideoSheetsHost
import com.example.ui.viewmodel.MainTab
import com.example.ui.viewmodel.MainViewModel
import com.example.ui.viewmodel.ScreenRoute

@OptIn(ExperimentalFoundationApi::class)
class MainActivity : ComponentActivity() {

    private val viewModel: MainViewModel by viewModels()

    // Apply the saved display language (English / Bangla / Hindi) to this Activity.
    override fun attachBaseContext(newBase: android.content.Context) {
        super.attachBaseContext(LocaleHelper.wrap(newBase, LocaleHelper.savedCode(newBase)))
    }

    private val mediaPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) {
        viewModel.refreshMedia()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        // Ask for media access so the library and Storage screen can scan real device files.
        val mediaPermissions = if (Build.VERSION.SDK_INT >= 33) {
            arrayOf(Manifest.permission.READ_MEDIA_VIDEO, Manifest.permission.READ_MEDIA_AUDIO, Manifest.permission.READ_MEDIA_IMAGES)
        } else {
            arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE)
        }
        if (mediaPermissions.any { ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED }) {
            mediaPermissionLauncher.launch(mediaPermissions)
        }

        // Handle "Open with EvaPlayer" from Intent
        handleIncomingIntent(intent)

        setContent {
            val settings by viewModel.settings.collectAsState()
            // If the chosen language differs from the one this screen was built with, rebuild it.
            androidx.compose.runtime.LaunchedEffect(settings.displayLanguage) {
                val wanted = LocaleHelper.codeFor(settings.displayLanguage)
                if (LocaleHelper.savedCode(this@MainActivity) != wanted) {
                    LocaleHelper.save(this@MainActivity, settings.displayLanguage)
                    recreate()
                }
            }
            val currentScreen by viewModel.currentScreen.collectAsState()
            val selectedTab by viewModel.selectedTab.collectAsState()

            // Back button: go to the previous screen instead of closing the app.
            // (The player and the Browser tab handle back themselves.)
            BackHandler(
                enabled = currentScreen !is ScreenRoute.Player &&
                    (currentScreen !is ScreenRoute.Main || selectedTab == MainTab.VIDEOS || selectedTab == MainTab.SETTINGS)
            ) {
                if (currentScreen !is ScreenRoute.Main) {
                    viewModel.navigateBack()
                } else {
                    viewModel.selectTab(MainTab.FOLDERS)
                }
            }

            // Back while videos are selected just cancels the selection
            val selectedUris by viewModel.selectedUris.collectAsState()
            BackHandler(enabled = selectedUris.isNotEmpty()) { viewModel.clearSelection() }

            EvaPlayerTheme(
                themeMode = settings.theme,
                accentColorName = settings.accentColor
            ) {
              // No stretch/lift overscroll effect, so the page never jumps while scrolling
              CompositionLocalProvider(LocalOverscrollConfiguration provides null) {
                when (val route = currentScreen) {
                    is ScreenRoute.Main -> {
                        HomeScreen(viewModel = viewModel, modifier = Modifier.fillMaxSize())
                    }
                    is ScreenRoute.FolderDetail -> {
                        FolderDetailScreen(
                            folderName = route.folderName,
                            folderPath = route.folderPath,
                            viewModel = viewModel,
                            modifier = Modifier.fillMaxSize()
                        )
                    }
                    is ScreenRoute.Music -> {
                        MusicScreen(viewModel = viewModel, modifier = Modifier.fillMaxSize())
                    }
                    is ScreenRoute.UrlStream -> {
                        UrlStreamScreen(viewModel = viewModel, modifier = Modifier.fillMaxSize())
                    }
                    is ScreenRoute.FileTransfer -> {
                        FileTransferScreen(viewModel = viewModel, modifier = Modifier.fillMaxSize())
                    }
                    is ScreenRoute.Playlists -> {
                        PlaylistsScreen(viewModel = viewModel, modifier = Modifier.fillMaxSize())
                    }
                    is ScreenRoute.Favorites -> {
                        FavoritesScreen(viewModel = viewModel, modifier = Modifier.fillMaxSize())
                    }
                    is ScreenRoute.HiddenVideos -> {
                        HiddenVideosScreen(viewModel = viewModel, modifier = Modifier.fillMaxSize())
                    }
                    is ScreenRoute.SubtitleSettings -> {
                        SubtitleSettingsScreen(viewModel = viewModel, modifier = Modifier.fillMaxSize())
                    }
                    is ScreenRoute.PrivacySettings -> {
                        PrivacySettingsScreen(viewModel = viewModel, modifier = Modifier.fillMaxSize())
                    }
                    is ScreenRoute.Storage -> {
                        StorageScreen(viewModel = viewModel, modifier = Modifier.fillMaxSize())
                    }
                    is ScreenRoute.Player -> {
                        EvaVideoPlayer(
                            initialVideo = route.video,
                            playlist = route.playlist,
                            startIndex = route.startIndex,
                            viewModel = viewModel,
                            modifier = Modifier.fillMaxSize()
                        )
                    }
                    else -> {
                        HomeScreen(viewModel = viewModel, modifier = Modifier.fillMaxSize())
                    }
                }
                // Three-dot menus and dialogs work on every screen
                VideoSheetsHost(viewModel = viewModel)
              }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIncomingIntent(intent)
    }

    private fun handleIncomingIntent(intent: Intent?) {
        if (intent == null) return
        val action = intent.action
        val data = intent.data
        if (action == Intent.ACTION_VIEW && data != null) {
            val urlString = data.toString()
            // The Koyeb link sends the real file name in the "title" extra (S.title in the intent URI)
            val extraTitle = intent.getStringExtra("title")
                ?: intent.getStringExtra(Intent.EXTRA_TITLE)
                ?: intent.getStringExtra("S.title")
            val filename = if (!extraTitle.isNullOrBlank()) extraTitle else (data.lastPathSegment ?: "External Video")
            // "Download From EvaPLAYER" link: open the app and start downloading instead of playing
            val wantsDownload = intent.getBooleanExtra("download", false) ||
                intent.getBooleanExtra("B.download", false)
            if (wantsDownload && (urlString.startsWith("http://") || urlString.startsWith("https://"))) {
                val dlName = if (filename.substringAfterLast('.', "").length in 2..4) filename else "$filename.mp4"
                val err = com.example.data.UrlDownloads.start(this, urlString, dlName)
                viewModel.showToast(err ?: "Download started")
                viewModel.navigateTo(ScreenRoute.UrlStream) // shows live download progress
                setIntent(Intent())
                return
            }
            val video = VideoItem(
                id = urlString,
                title = filename,
                path = urlString,
                uriString = urlString,
                durationMs = 0L,
                sizeBytes = 0L,
                dateModified = System.currentTimeMillis() / 1000,
                folderName = "External",
                folderPath = "external",
                format = filename.substringAfterLast('.', "").let { ext ->
                    if (ext.length in 2..4 && ext.all { it.isLetterOrDigit() }) ext.uppercase() else "MKV"
                },
                isStream = urlString.startsWith("http://") || urlString.startsWith("https://")
            )
            viewModel.navigateTo(ScreenRoute.Player(video = video))
            // Do not replay the same link when the Activity is recreated (e.g. language change)
            setIntent(Intent())
        }
    }
}
