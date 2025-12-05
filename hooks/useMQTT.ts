import { useContext } from 'react';
import { MQTTContext } from '../context/MQTTContext';
import { MQTTContextType } from '../types/mqtt.types';

/**
 * Custom hook to access MQTT context
 * Must be used within MQTTProvider
 */
export const useMQTT = (): MQTTContextType => {
    const context = useContext(MQTTContext);
    if (!context) {
        throw new Error('useMQTT must be used within a MQTTProvider');
    }
    return context;
};
