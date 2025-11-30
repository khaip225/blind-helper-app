import { Tabs } from 'expo-router';
import React from 'react';

import { HapticTab } from '@/components/haptic-tab';
import { IconSymbol } from '@/components/ui/icon-symbol';
import { Colors } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';

export default function TabLayout() {
  const colorScheme = useColorScheme();

  return (
      <Tabs
        screenOptions={{
          tabBarActiveTintColor: Colors[colorScheme ?? 'light'].tint,
          headerShown: false,
          tabBarButton: HapticTab,
        }}>
        <Tabs.Screen
          name="index"
          options={{
            title: 'Home',
            tabBarIcon: ({ color }) => <IconSymbol size={28} name="house.fill" color={color} />,
          }}
        />
        <Tabs.Screen
          name="explore"
          options={{
            href: null, // Ẩn khỏi tab bar
            title: 'Explore',
            tabBarIcon: ({ color }) => <IconSymbol size={28} name="paperplane.fill" color={color} />,
          }}
        />
        <Tabs.Screen
          name="map"
          options={{
            title: 'Map',
            tabBarIcon: ({ color }) => <IconSymbol size={28} name="map.fill" color={color} />,
          }}
        />
        <Tabs.Screen
          name="alert"
          options={{
            href: null, // Ẩn khỏi tab bar
            title: 'Alerts',
          }}
        />
        <Tabs.Screen
          name="sos"
          options={{
            title: 'SOS',
            tabBarIcon: ({ color }) => <IconSymbol size={28} name="sos.fill" color={color} />,
          }}
        /> 
        <Tabs.Screen
          name="setting"
          options={{
            href: null, // Ẩn khỏi tab bar
            title: 'Settings',
          }}
        />
        <Tabs.Screen
          name="notificationSetting"
          options={{
            href: null, // Ẩn khỏi tab bar
            title: 'Notification Settings',
          }}
        />
        <Tabs.Screen
          name="call"
          options={{
            href: null, // Ẩn khỏi tab bar
            title: 'Call',
          }}
        />

      </Tabs>
  );
}
