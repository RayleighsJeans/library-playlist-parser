#!/usr/bin/env python3
"""
Test script to search for Wikipedia best-selling albums on streaming services.
Uses the new class-based API for easy integration with Jupyter notebooks.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path to import the module
sys.path.insert(0, str(Path(__file__).parent.parent))

from find_albums_on_streaming import StreamingSearcher


def main():
    """Search for Wikipedia best-selling albums on streaming services."""
    
    # Load Wikipedia albums dataset
    dataset_path = Path(__file__).parent / 'wikipedia_bestselling_albums.json'
    with open(dataset_path, 'r') as f:
        albums = json.load(f)
    
    print("🎵 Wikipedia Best-Selling Albums - Streaming Service Search")
    print("=" * 80)
    print(f"\nSearching for {len(albums)} albums...\n")
    
    # Initialize searcher
    searcher = StreamingSearcher()
    
    # Search for each album
    results = []
    for i, album_data in enumerate(albums, 1):
        artist = album_data['artist']
        album = album_data['album']
        year = album_data['year']
        sales = album_data['sales_millions']
        
        print(f"[{i}/{len(albums)}] {artist} - {album} ({year}) - {sales}M sales")
        
        # Search all services
        service_results = searcher.search_all_services(artist, album)
        
        # Display results
        found_services = []
        for service, url in service_results.items():
            if url:
                found_services.append(service)
                print(f"  ✓ {service.capitalize()}: {url}")
        
        if not found_services:
            print(f"  ✗ Not found on any service")
        
        results.append({
            'artist': artist,
            'album': album,
            'year': year,
            'sales_millions': sales,
            'services': service_results,
            'found_count': len(found_services)
        })
        
        print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    total_albums = len(results)
    albums_found = sum(1 for r in results if r['found_count'] > 0)
    
    print(f"\nTotal albums searched: {total_albums}")
    print(f"Albums found on at least one service: {albums_found} ({albums_found/total_albums*100:.1f}%)")
    print(f"Albums not found: {total_albums - albums_found}")
    
    # Service breakdown
    print("\nService breakdown:")
    service_counts = {}
    for result in results:
        for service, url in result['services'].items():
            if url:
                service_counts[service] = service_counts.get(service, 0) + 1
    
    for service in sorted(service_counts.keys()):
        count = service_counts[service]
        print(f"  {service.capitalize()}: {count}/{total_albums} ({count/total_albums*100:.1f}%)")
    
    print("\n" + "=" * 80)


if __name__ == '__main__':
    main()

# Made with Bob
