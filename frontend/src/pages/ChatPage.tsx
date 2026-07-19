import React from 'react'
import ChatInterface from '../components/ChatInterface'

const ChatPage: React.FC = () => {
  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-stone-50">
      <ChatInterface />
    </div>
  )
}

export default ChatPage
