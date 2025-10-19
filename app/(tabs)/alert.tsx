import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import React from "react";
import { FlatList, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { SafeAreaView } from 'react-native-safe-area-context';

export default function AlertScreen() {
  const router = useRouter();
  type NotificationItem = {
    id: string;
    title: string;
    time?: string;
    desc?: string;
    ago?: string;
    section?: string;
    isSection: boolean;
};

  // Mock data thông báo với sections
  const notifications: NotificationItem[] = [
    {
      id: "1",
      title: "⚠️ SOS Khẩn Cấp",
      time: "19:00",
      desc: "nhấn để xem vị trí",
      ago: "2 M",
      section: "Hôm nay",
      isSection: false,
    },
    {
      id: "2",
      title: "🔋 Pin Yếu (10%)",
      time: "8:50",
      desc: "nhấn để xem vị trí",
      ago: "2 H",
      section: "Hôm nay",
      isSection: false,
    },
    {
      id: "3",
      title: "📦 Vật Cản Lớn Phía Trước",
      time: "18:45",
      desc: "nhấn để xem vị trí",
      ago: "3 H",
      section: "Hôm nay",
      isSection: false,
    },
    {
      id: "section-yesterday",
      title: "Hôm qua",
      isSection: true,
    },
    {
      id: "4",
      title: "🔋 Pin Yếu (10%)",
      time: "8:45",
      desc: "nhấn để xem vị trí",
      ago: "1 D",
      section: "Hôm qua",
      isSection: false,
    },
    {
      id: "section-august",
      title: "15 August",
      isSection: true,
    },
    {
      id: "5",
      title: "⚠️ SOS Khẩn Cấp",
      time: "12:45",
      desc: "nhấn để xem vị trí",
      ago: "8 D",
      section: "15 August",
      isSection: false,
    },
  ];

  const renderNotificationItem = ({ item }: { item: NotificationItem }) => {
    if (item.isSection) {
      return (
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionText}>{item.title}</Text>
        </View>
      );
    }

    return (
      <TouchableOpacity style={styles.notificationItem}>
        <View style={styles.iconContainer}>
          <Ionicons name="notifications" size={24} color="#4169E1" />
        </View>
        <View style={styles.contentContainer}>
          <View style={styles.titleRow}>
            <Text style={styles.notificationTitle}>{item.title}</Text>
            <Text style={styles.timeAgo}>{item.ago}</Text>
          </View>
          <Text style={styles.notificationDesc}>
            {item.time} • {item.desc}
          </Text>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="chevron-back" size={24} color="#4169E1" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Cảnh Báo</Text>
        <View style={styles.newsTag}>
          <Text style={styles.newsText}>News</Text>
        </View>
      </View>

      {/* Section Header - Hôm nay */}
      <View style={styles.todaySection}>
        <Text style={styles.todaySectionText}>Hôm nay</Text>
      </View>

      {/* Danh sách thông báo */}
      <FlatList
        data={notifications}
        keyExtractor={(item) => item.id}
        renderItem={renderNotificationItem}
        showsVerticalScrollIndicator={false}
        style={styles.list}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8f9fa',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  backButton: {
    padding: 4,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#4169E1',
    flex: 1,
    textAlign: 'center',
    marginHorizontal: 16,
  },
  newsTag: {
    backgroundColor: '#e3f2fd',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  newsText: {
    fontSize: 12,
    color: '#4169E1',
    fontWeight: '500',
  },
  todaySection: {
    backgroundColor: '#e8f4ff',
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  todaySectionText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#4169E1',
  },
  sectionHeader: {
    backgroundColor: '#e8f4ff',
    paddingHorizontal: 16,
    paddingVertical: 8,
    marginTop: 8,
  },
  sectionText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#4169E1',
  },
  list: {
    flex: 1,
  },
  notificationItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    paddingVertical: 16,
    paddingHorizontal: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#f5f5f5',
  },
  iconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#e3f2fd',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  contentContainer: {
    flex: 1,
  },
  titleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  notificationTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    flex: 1,
  },
  timeAgo: {
    fontSize: 12,
    color: '#999',
  },
  notificationDesc: {
    fontSize: 14,
    color: '#666',
  },
});
