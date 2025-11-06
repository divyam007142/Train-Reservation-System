"""Core data structures for Railway Reservation System"""

class Node:
    """Node for Linked List"""
    def __init__(self, data):
        self.data = data
        self.next = None

class LinkedList:
    """Linked List implementation for train records"""
    def __init__(self):
        self.head = None
    
    def insert_at_end(self, data):
        """Insert node at end of list"""
        new_node = Node(data)
        if not self.head:
            self.head = new_node
            return
        
        current = self.head
        while current.next:
            current = current.next
        current.next = new_node
    
    def delete_by_value(self, key, compare_func):
        """Delete node by comparing with key using compare_func"""
        if not self.head:
            return False
        
        # If head needs to be deleted
        if compare_func(self.head.data, key):
            self.head = self.head.next
            return True
        
        current = self.head
        while current.next:
            if compare_func(current.next.data, key):
                current.next = current.next.next
                return True
            current = current.next
        return False
    
    def search(self, key, compare_func):
        """Search for a node using compare_func"""
        current = self.head
        while current:
            if compare_func(current.data, key):
                return current.data
            current = current.next
        return None
    
    def get_all(self):
        """Get all elements as list"""
        result = []
        current = self.head
        while current:
            result.append(current.data)
            current = current.next
        return result
    
    def update(self, key, new_data, compare_func):
        """Update node data"""
        current = self.head
        while current:
            if compare_func(current.data, key):
                current.data = new_data
                return True
            current = current.next
        return False

class Queue:
    """Queue implementation for waiting list"""
    def __init__(self):
        self.items = []
    
    def enqueue(self, item):
        """Add item to queue"""
        self.items.append(item)
    
    def dequeue(self):
        """Remove and return first item"""
        if not self.is_empty():
            return self.items.pop(0)
        return None
    
    def peek(self):
        """Get first item without removing"""
        if not self.is_empty():
            return self.items[0]
        return None
    
    def is_empty(self):
        """Check if queue is empty"""
        return len(self.items) == 0
    
    def size(self):
        """Get queue size"""
        return len(self.items)
    
    def get_all(self):
        """Get all items in queue"""
        return self.items.copy()
