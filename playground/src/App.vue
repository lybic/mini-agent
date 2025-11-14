<script setup lang="ts">
import { NLayout, NLayoutHeader, NLayoutContent, NGrid, NGi, NMessageProvider, NDialogProvider } from 'naive-ui'
import Header from './components/Header.vue'
import StreamingView from './components/StreamingView.vue'
import InteractionView from './components/InteractionView.vue'
</script>

<template>
  <n-message-provider>
    <n-dialog-provider>
      <n-layout style="height: 100vh">
        <n-layout-header
          style="height: 64px; padding: 0 24px; display: flex; align-items: center"
          bordered
        >
          <Header />
        </n-layout-header>
        <n-layout-content style="height: calc(100% - 64px)">
          <n-grid :cols="4" style="height: 100%">
            <n-gi
              :span="3"
              style="display: flex; align-items: center; justify-content: center; height: 100%"
            >
              <StreamingView />
            </n-gi>
            <n-gi
              :span="1"
              style="display: flex; align-items: center; justify-content: center; height: 100%"
            >
              <InteractionView />
            </n-gi>
          </n-grid>
        </n-layout-content>
      </n-layout>
    </n-dialog-provider>
  </n-message-provider>
</template>

<style scoped></style>
