"use client";

import { APIProvider, Map, Marker } from "@vis.gl/react-google-maps";

export default function OfficeMap() {
    const position = { lat: 37.7749, lng: -122.4194 }; // Default to San Francisco
    const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;

    if (!apiKey) {
        return (
            <div className="w-full h-96 bg-muted flex items-center justify-center rounded-lg">
                <p className="text-muted-foreground text-center p-4">
                    Google Maps requires an API key. Please add <br />
                    <code className="bg-gray-300 p-1 rounded">NEXT_PUBLIC_GOOGLE_MAPS_API_KEY</code> <br />
                    to your environment variables.
                </p>
            </div>
        );
    }
    
    return (
        <APIProvider apiKey={apiKey}>
            <div className="w-full h-96">
                <Map
                    defaultCenter={position}
                    defaultZoom={13}
                    gestureHandling={'greedy'}
                    disableDefaultUI={true}
                    mapId="nestedge-map"
                >
                    <Marker position={position} />
                </Map>
            </div>
        </APIProvider>
    );
}
