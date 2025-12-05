// Audio Manager - Speaker control & Ringtone management
// Uses InCallManager for audio routing control

let InCallManager: any = null;

// Try to load InCallManager
try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const incallModule = require('react-native-incall-manager');
    InCallManager = incallModule?.default || incallModule;
    console.log('[Audio] InCallManager loaded:', typeof InCallManager);
} catch (err) {
    console.warn('[Audio] react-native-incall-manager not installed:', err);
}

/**
 * Check if InCallManager is available
 */
export const isInCallManagerAvailable = (): boolean => {
    return InCallManager !== null && typeof InCallManager === 'object';
};

/**
 * Start audio session for video call
 * Initializes InCallManager but doesn't force speaker
 */
export const startAudioSession = () => {
    if (!isInCallManagerAvailable()) {
        console.warn('[Audio] ⚠️ InCallManager not available');
        return;
    }

    try {
        console.log('[Audio] 📞 Starting InCallManager session...');
        InCallManager.start({ media: 'video', ringback: '' });
        console.log('[Audio] ✅ InCallManager session started');
    } catch (err) {
        console.error('[Audio] ❌ Failed to start InCallManager:', err);
    }
};

/**
 * Stop audio session
 */
export const stopAudioSession = () => {
    if (!isInCallManagerAvailable()) return;

    try {
        InCallManager.stop();
        console.log('[Audio] 🔇 Audio session stopped');
    } catch (err) {
        console.warn('[Audio] Failed to stop audio session:', err);
    }
};

/**
 * Enable speakerphone
 */
export const enableSpeaker = () => {
    if (!isInCallManagerAvailable()) {
        console.warn('[Audio] ⚠️ InCallManager not available - cannot enable speaker');
        return;
    }

    try {
        if (typeof InCallManager.setForceSpeakerphoneOn === 'function') {
            InCallManager.setForceSpeakerphoneOn(true);
            console.log('[Audio] 🔊 Speakerphone enabled');
        }
    } catch (err) {
        console.error('[Audio] ❌ Failed to enable speaker:', err);
    }
};

/**
 * Disable speakerphone
 */
export const disableSpeaker = () => {
    if (!isInCallManagerAvailable()) return;

    try {
        if (typeof InCallManager.setForceSpeakerphoneOn === 'function') {
            InCallManager.setForceSpeakerphoneOn(false);
            console.log('[Audio] 🔇 Speakerphone disabled');
        }
    } catch (err) {
        console.warn('[Audio] Failed to disable speaker:', err);
    }
};

/**
 * Start ringtone for incoming call
 * @param ringtone - Name of ringtone ('default' or custom)
 */
export const startRingtone = (ringtone: string = 'default') => {
    if (!isInCallManagerAvailable()) return;

    try {
        console.log('[Audio] 🔔 Starting ringtone for incoming call');
        // Ensure audio session is active
        InCallManager.start({ media: 'video' });
        
        // Use built-in ringtone if available
        if (typeof InCallManager.startRingtone === 'function') {
            InCallManager.startRingtone(ringtone);
        } else {
            // Fallback: enable speakerphone so sound is audible
            enableSpeaker();
        }
    } catch (err) {
        console.warn('[Audio] Failed to start ringtone:', err);
    }
};

/**
 * Stop ringtone
 */
export const stopRingtone = () => {
    if (!isInCallManagerAvailable()) return;

    try {
        if (typeof InCallManager.stopRingtone === 'function') {
            InCallManager.stopRingtone();
            console.log('[Audio] 🔕 Ringtone stopped');
        }
    } catch (err) {
        console.warn('[Audio] Failed to stop ringtone:', err);
    }
};

/**
 * Cleanup audio on hangup
 */
export const cleanupAudio = () => {
    disableSpeaker();
    stopRingtone();
    stopAudioSession();
    console.log('[Audio] ✅ Audio cleanup complete');
};
