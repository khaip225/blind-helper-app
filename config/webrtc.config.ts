// --- TURN Configuration ---
// RTCIceServer type definition
interface RTCIceServer {
    urls: string | string[];
    username?: string;
    credential?: string;
}
const METERED_API_KEY = '6cc0b031d2951fbd7ac079906c6b0470b02a';
const METERED_API_URL = `https://pbl6.metered.live/api/v1/turn/credentials?apiKey=${METERED_API_KEY}`;

// Cache for TURN credentials (fetch once and reuse)
let cachedIceServers: RTCIceServer[] | null = null;
let fetchingIceServers: Promise<RTCIceServer[]> | null = null;

/**
 * Fetch TURN credentials from Metered.ca API
 * Caches credentials to avoid repeated fetches
 */
export const fetchTurnCredentials = async (): Promise<RTCIceServer[]> => {
    // Return cached if available
    if (cachedIceServers) {
        console.log('[TURN] Using cached credentials');
        return cachedIceServers;
    }
    
    // Return in-flight request if already fetching
    if (fetchingIceServers) {
        console.log('[TURN] Waiting for in-flight fetch');
        return fetchingIceServers;
    }
    
    // Start new fetch
    fetchingIceServers = (async () => {
        try {
            console.log('[TURN] Fetching credentials from Metered.ca...');
            const response = await fetch(METERED_API_URL, {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' },
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const iceServers = await response.json();
            console.log('[TURN] ✅ Fetched credentials:', iceServers.length, 'servers');
            
            // Log server types for debugging
            iceServers.forEach((server: any) => {
                const urls = Array.isArray(server.urls) ? server.urls : [server.urls];
                urls.forEach((url: string) => {
                    if (url.startsWith('stun:')) {
                        console.log('[TURN] 🌐 STUN:', url);
                    } else if (url.startsWith('turn:')) {
                        console.log('[TURN] 🔄 TURN:', url);
                    }
                });
            });
            
            // Cache for reuse
            cachedIceServers = iceServers;
            return iceServers;
        } catch (error) {
            console.error('[TURN] ❌ Failed to fetch credentials:', error);
            // Fallback to Google STUN
            console.log('[TURN] 📡 Falling back to Google STUN');
            return [
                { urls: 'stun:stun.l.google.com:19302' },
                { urls: 'stun:stun1.l.google.com:19302' },
            ];
        } finally {
            fetchingIceServers = null;
        }
    })();
    
    return fetchingIceServers;
};

/**
 * Get WebRTC peer connection configuration with TURN credentials
 */
export const getConfiguration = async () => {
    const iceServers = await fetchTurnCredentials();
    return {
        iceServers,
        iceTransportPolicy: 'all' as const,
        iceCandidatePoolSize: 10,
    };
};

/**
 * Clear cached TURN credentials (useful for testing or forcing refresh)
 */
export const clearTurnCache = () => {
    cachedIceServers = null;
    fetchingIceServers = null;
    console.log('[TURN] Cache cleared');
};
