import type { Property } from '@/types';
import Image from 'next/image';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { BedDouble, Bath, MapPin } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface PropertyListProps {
  properties: Property[];
}

export function PropertyList({ properties }: PropertyListProps) {
    if (properties.length === 0) {
        return (
            <div className="text-center py-16 text-muted-foreground">
                <h3 className="font-headline text-2xl">No Properties Found</h3>
                <p>Try adjusting your filters to find more results.</p>
            </div>
        )
    }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
      {properties.map((property) => (
        <Card key={property.id} className="overflow-hidden shadow-lg hover:shadow-xl transition-shadow duration-300 flex flex-col">
          <CardHeader className="p-0 relative">
            <Image
              src={property.imageUrl}
              alt={property.title}
              width={600}
              height={400}
              className="w-full h-48 object-cover"
              data-ai-hint={property.dataHint}
            />
            <Badge className="absolute top-2 right-2" variant={property.type === 'sale' ? 'default' : 'secondary'}>
              For {property.type}
            </Badge>
          </CardHeader>
          <CardContent className="p-4 flex-grow">
            <CardTitle className="font-headline text-lg mb-2 leading-tight">{property.title}</CardTitle>
            <p className="text-sm text-muted-foreground flex items-center gap-1"><MapPin className="w-4 h-4" />{property.location}</p>
            <p className="font-bold text-lg text-primary mt-2">
                {property.type === 'sale' ? `$${property.price.toLocaleString()}` : `$${property.price.toLocaleString()}/month`}
            </p>
          </CardContent>
          <CardFooter className="p-4 bg-secondary/50 flex justify-between items-center text-sm">
            <div className="flex gap-4 text-muted-foreground">
                <span className="flex items-center gap-1"><BedDouble className="w-4 h-4" /> {property.bedrooms}</span>
                <span className="flex items-center gap-1"><Bath className="w-4 h-4" /> {property.bathrooms}</span>
            </div>
             <Button size="sm" variant="outline">Details</Button>
          </CardFooter>
        </Card>
      ))}
    </div>
  );
}
