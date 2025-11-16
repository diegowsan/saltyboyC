/**
 * Set debug information for background scripts
 *
 * @param {boolean} debugEnabled
 * @returns
 */
function setDebugSettings(debugEnabled) {
    return new Promise((res) => {
        chrome.storage.local.set(
            {
                debugSettings: {
                    debugEnabled: debugEnabled,
                },
            },
            () => {
                res()
            }
        )
    })
}

/**
 * Get the current debug settings
 *
 * @returns {object} - Should be an object of the following form:
 *  ```
 *  {
 *      "debugEnabled": boolean
 *  }
 */
function getDebugSettings() {
    return new Promise((res) => {
        chrome.storage.local.get(['debugSettings'], (result) => {
            res(result.debugSettings)
        })
    })
}

/**
 * Initializes the match status
 */
/**
 * Initializes the match status
 */
function initializeDebugSettings() {
    return getDebugSettings().then((debugSettings) => {
        const defaultSettings = { debugEnabled: false }

        if (debugSettings == null || debugSettings == undefined) {
            // Set default and return the default object
            return setDebugSettings(false).then(() => {
                return defaultSettings
            })
        }

        if (!debugSettings.hasOwnProperty('debugEnabled')) {
            // Set default and return the default object
            return setDebugSettings(false).then(() => {
                return defaultSettings
            })
        }

        // Settings are valid, just return them
        return debugSettings
    })
}

export { getDebugSettings, setDebugSettings, initializeDebugSettings }
