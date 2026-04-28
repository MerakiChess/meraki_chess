#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Import the MainFrame class to test the method
from chess_engine.gui.wxgui import MainFrame # type: ignore

def test_equilibrium_calculation():
    """Test the equilibrium point calculation logic"""
    # Create a mock MainFrame instance (without GUI)
    frame = MainFrame.__new__(MainFrame)  # Create instance without calling __init__

    # Test data: depths and average metrics
    depths = [1, 2, 3, 4, 5]
    elapsed_avg = [0.1, 0.3, 0.8, 2.5, 8.0]  # Execution times
    rss_avg = [1.0, 2.5, 4.0, 7.0, 15.0]     # Memory deltas
    cpu_avg = [10.0, 25.0, 45.0, 80.0, 95.0] # CPU usage

    # Calculate equilibrium point
    equilibrium = frame._calculate_equilibrium_point(depths, elapsed_avg, rss_avg, cpu_avg)

    print("Test Data:")
    print(f"Depths: {depths}")
    print(f"Elapsed times: {elapsed_avg}")
    print(f"Memory deltas: {rss_avg}")
    print(f"CPU usage: {cpu_avg}")
    print(f"\nCalculated Equilibrium Point: {equilibrium}")

    # Calculate sums for each depth
    sums = [elapsed_avg[i] + rss_avg[i] + cpu_avg[i] for i in range(len(depths))]
    print(f"Sums: {sums}")

    # Expected: Depth with minimum sum
    min_sum_index = sums.index(min(sums))
    expected = depths[min_sum_index]
    print(f"Expected (min sum at depth): {expected}")
    if equilibrium == expected:
        print("✓ Equilibrium calculation PASSED")
        return True
    else:
        print(f"✗ Equilibrium calculation FAILED (expected {expected}, got {equilibrium})")
        return False

if __name__ == "__main__":
    success = test_equilibrium_calculation()
    sys.exit(0 if success else 1)
