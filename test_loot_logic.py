#!/usr/bin/env python3
"""
Simple local tests for loot distribution logic
Run with: python test_loot_logic.py
"""

from collections import defaultdict


def calculate_loot_distribution(loot_items, participant_count):
    """Test the loot distribution logic locally"""
    loot_summary = defaultdict(int)
    
    # Simulate loot items
    for item in loot_items:
        loot_summary[item['name']] += item['quantity']
    
    distribution = {}
    for item_name, total_quantity in loot_summary.items():
        per_person = total_quantity // participant_count
        remainder = total_quantity % participant_count
        
        distribution[item_name] = {
            'total': total_quantity,
            'per_person': per_person,
            'remainder': remainder
        }
    
    return distribution


def test_distribution():
    """Test various loot distribution scenarios"""
    
    # Test case 1: Even distribution
    loot_items = [
        {'name': 'Gold Coins', 'quantity': 60},
        {'name': 'Magic Sword', 'quantity': 3}
    ]
    participants = 3
    
    result = calculate_loot_distribution(loot_items, participants)
    
    print("🧪 Test Case 1: Even distribution")
    print(f"Participants: {participants}")
    print("Loot items:", loot_items)
    print("Distribution:")
    for item, dist in result.items():
        if dist['remainder'] > 0:
            print(f"  {dist['total']}x {item} → {dist['per_person']} each + {dist['remainder']} extra")
        else:
            print(f"  {dist['total']}x {item} → {dist['per_person']} each")
    print()
    
    # Test case 2: Uneven distribution
    loot_items = [
        {'name': 'Dragon Scale', 'quantity': 7},
        {'name': 'Health Potion', 'quantity': 13}
    ]
    participants = 4
    
    result = calculate_loot_distribution(loot_items, participants)
    
    print("🧪 Test Case 2: Uneven distribution")
    print(f"Participants: {participants}")
    print("Loot items:", loot_items)
    print("Distribution:")
    for item, dist in result.items():
        if dist['remainder'] > 0:
            print(f"  {dist['total']}x {item} → {dist['per_person']} each + {dist['remainder']} extra")
        else:
            print(f"  {dist['total']}x {item} → {dist['per_person']} each")
    print()


if __name__ == "__main__":
    print("🎯 Testing Loot Distribution Logic Locally\n")
    test_distribution()
    print("✅ Local tests completed!")
