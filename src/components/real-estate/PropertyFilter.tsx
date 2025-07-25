"use client";

import { useState, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Search, X } from 'lucide-react';
import type { Property } from '@/types';
import { PropertyList } from './PropertyList';

const mockProperties: Property[] = [
  { id: '1', title: 'Modern Downtown Loft', price: 450000, location: 'New York', bedrooms: 1, bathrooms: 1, imageUrl: 'https://placehold.co/600x400', type: 'sale', dataHint: 'modern apartment' },
  { id: '2', title: 'Suburban Family Home', price: 650000, location: 'San Francisco', bedrooms: 4, bathrooms: 3, imageUrl: 'https://placehold.co/600x400', type: 'sale', dataHint: 'suburban house' },
  { id: '3', title: 'Chic Studio Apartment', price: 2500, location: 'New York', bedrooms: 0, bathrooms: 1, imageUrl: 'https://placehold.co/600x400', type: 'rent', dataHint: 'studio apartment' },
  { id: '4', title: 'Spacious Villa with Pool', price: 1200000, location: 'Los Angeles', bedrooms: 5, bathrooms: 5, imageUrl: 'https://placehold.co/600x400', type: 'sale', dataHint: 'luxury villa' },
  { id: '5', title: 'Cozy Garden Flat', price: 3200, location: 'San Francisco', bedrooms: 2, bathrooms: 1, imageUrl: 'https://placehold.co/600x400', type: 'rent', dataHint: 'cozy apartment' },
  { id: '6', title: 'Penthouse with a View', price: 8000, location: 'Los Angeles', bedrooms: 3, bathrooms: 3, imageUrl: 'https://placehold.co/600x400', type: 'rent', dataHint: 'luxury penthouse' },
  { id: '7', title: 'Beachfront Bungalow', price: 950000, location: 'Miami', bedrooms: 2, bathrooms: 2, imageUrl: 'https://placehold.co/600x400', type: 'sale', dataHint: 'beach house' },
  { id: '8', title: 'Affordable Townhouse', price: 380000, location: 'Miami', bedrooms: 3, bathrooms: 2, imageUrl: 'https://placehold.co/600x400', type: 'sale', dataHint: 'townhouse exterior' },
];

const initialFilters = {
    location: 'all',
    type: 'all',
    price: [0, 1500000],
    bedrooms: 'all',
};

export default function PropertyFilter() {
  const [filters, setFilters] = useState(initialFilters);

  const handleReset = () => {
    setFilters(initialFilters);
  };

  const filteredProperties = useMemo(() => {
    return mockProperties.filter(property => {
      const priceToCompare = filters.type === 'rent' ? property.price / 200 : property.price; // Simplified rent/buy price comparison
      
      return (
        (filters.location === 'all' || property.location === filters.location) &&
        (filters.type === 'all' || property.type === filters.type) &&
        (priceToCompare >= filters.price[0] && priceToCompare <= filters.price[1]) &&
        (filters.bedrooms === 'all' || property.bedrooms >= parseInt(filters.bedrooms))
      );
    });
  }, [filters]);

  return (
    <div className="space-y-8">
        <div className="text-center">
            <h2 className="font-headline text-3xl font-bold flex items-center justify-center gap-3"><Search /> Find Your Next Property</h2>
            <p className="mt-2 text-lg text-muted-foreground">Use our dynamic filters to find the perfect match.</p>
        </div>
        <Card className="shadow-xl">
            <CardContent className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 gap-4 items-end">
                <div className="space-y-2">
                <Label htmlFor="location">Location</Label>
                <Select value={filters.location} onValueChange={(value) => setFilters(f => ({...f, location: value}))}>
                    <SelectTrigger id="location">
                    <SelectValue placeholder="Select location" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">All Locations</SelectItem>
                        <SelectItem value="New York">New York</SelectItem>
                        <SelectItem value="San Francisco">San Francisco</SelectItem>
                        <SelectItem value="Los Angeles">Los Angeles</SelectItem>
                        <SelectItem value="Miami">Miami</SelectItem>
                    </SelectContent>
                </Select>
                </div>
                <div className="space-y-2">
                <Label htmlFor="type">Type</Label>
                <Select value={filters.type} onValueChange={(value) => setFilters(f => ({...f, type: value}))}>
                    <SelectTrigger id="type">
                    <SelectValue placeholder="For Sale or Rent" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">For Sale or Rent</SelectItem>
                        <SelectItem value="sale">For Sale</SelectItem>
                        <SelectItem value="rent">For Rent</SelectItem>
                    </SelectContent>
                </Select>
                </div>
                <div className="space-y-2">
                <Label htmlFor="bedrooms">Bedrooms</Label>
                 <Select value={String(filters.bedrooms)} onValueChange={(value) => setFilters(f => ({...f, bedrooms: value}))}>
                    <SelectTrigger id="bedrooms">
                    <SelectValue placeholder="Any" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Any</SelectItem>
                        <SelectItem value="1">1+</SelectItem>
                        <SelectItem value="2">2+</SelectItem>
                        <SelectItem value="3">3+</SelectItem>
                        <SelectItem value="4">4+</SelectItem>
                        <SelectItem value="5">5+</SelectItem>
                    </SelectContent>
                </Select>
                </div>
                <div className="space-y-2 lg:col-span-2 xl:col-span-1">
                    <Label htmlFor="price">Price Range</Label>
                    <Slider
                        id="price"
                        min={0}
                        max={1500000}
                        step={50000}
                        value={filters.price}
                        onValueChange={(value) => setFilters(f => ({...f, price: value as [number, number]}))}
                    />
                    <div className="flex justify-between text-xs text-muted-foreground">
                        <span>${filters.price[0].toLocaleString()}</span>
                        <span>${filters.price[1].toLocaleString()}</span>
                    </div>
                </div>
                <div className="lg:col-span-full xl:col-span-1">
                    <Button onClick={handleReset} variant="outline" className="w-full">
                        <X className="w-4 h-4 mr-2"/>
                        Reset Filters
                    </Button>
                </div>
            </div>
            </CardContent>
        </Card>

        <div>
            <PropertyList properties={filteredProperties} />
        </div>
    </div>
  );
}
