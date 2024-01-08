import { Notice, Plugin, request } from 'obsidian';
import { KhojSetting, KhojSettingTab, DEFAULT_SETTINGS } from 'src/settings'
import { KhojSearchModal } from 'src/search_modal'
import { KhojChatModal } from 'src/chat_modal'
import { updateContentIndex } from './utils';


export default class Khoj extends Plugin {
    settings: KhojSetting;
    indexingTimer: NodeJS.Timeout;

    async onload() {
        await this.loadSettings();

        // Add search command. It can be triggered from anywhere
        this.addCommand({
            id: 'search',
            name: 'Search',
            checkCallback: (checking) => {
                if (!checking && this.settings.connectedToBackend)
                    new KhojSearchModal(this.app, this.settings).open();
                return this.settings.connectedToBackend;
            }
        });

        // Add similar notes command. It can only be triggered from the editor
        this.addCommand({
            id: 'similar',
            name: 'Find similar notes',
            editorCheckCallback: (checking) => {
                if (!checking && this.settings.connectedToBackend)
                    new KhojSearchModal(this.app, this.settings, true).open();
                return this.settings.connectedToBackend;
            }
        });

        // Add chat command. It can be triggered from anywhere
        this.addCommand({
            id: 'chat',
            name: 'Chat',
            checkCallback: (checking) => {
                if (!checking && this.settings.connectedToBackend)
                    new KhojChatModal(this.app, this.settings).open();
                return this.settings.connectedToBackend;
            }
        });

        // Create an icon in the left ribbon.
        this.addRibbonIcon('search', 'Khoj', (_: MouseEvent) => {
            // Called when the user clicks the icon.
            this.settings.connectedToBackend
                ? new KhojSearchModal(this.app, this.settings).open()
                : new Notice(`❗️Ensure Khoj backend is running and Khoj URL is pointing to it in the plugin settings`);
        });

        // Add a settings tab so the user can configure khoj
        this.addSettingTab(new KhojSettingTab(this.app, this));

        // Add scheduled job to update index every 60 minutes
        this.indexingTimer = setInterval(async () => {
            if (this.settings.autoConfigure) {
                this.settings.lastSyncedFiles = await updateContentIndex(
                    this.app.vault, this.settings, this.settings.lastSyncedFiles
                );
            }
        }, 60 * 60 * 1000);
    }

    async loadSettings() {
        // Load khoj obsidian plugin settings
        this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());

        // Check if khoj backend is configured, note if cannot connect to backend
        let headers = { "Authorization": `Bearer ${this.settings.khojApiKey}` };

        if (this.settings.khojApiKey === "" && this.settings.khojUrl === "https://app.khoj.dev") {
            new Notice(`❗️Khoj API key is not configured. Please visit https://app.khoj.dev/config#clients to get an API key.`);
            return;
        }

        await request({ url: this.settings.khojUrl ,method: "GET", headers: headers })
            .then(response => {
                this.settings.connectedToBackend = true;
            })
            .catch(error => {
                this.settings.connectedToBackend = false;
                new Notice(`❗️Ensure Khoj backend is running and Khoj URL is pointing to it in the plugin settings.\n\n${error}`);
            });
    }

    async saveSettings() {
        this.saveData(this.settings);
    }

    async onunload() {
        // Remove scheduled job to update index at regular cadence
        if (this.indexingTimer)
            clearInterval(this.indexingTimer);

        this.unload();
    }
}
