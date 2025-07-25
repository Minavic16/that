import Image from 'next/image';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Users, MapPin, Search, BarChart2 } from 'lucide-react';
import Link from 'next/link';
import { Carousel, CarouselContent, CarouselItem, CarouselNext, CarouselPrevious } from '@/components/ui/carousel';
import PropertyFilter from '@/components/real-estate/PropertyFilter';

const features = [
  { icon: <Search className="w-6 h-6 text-accent" />, text: 'Filterable property listings' },
  { icon: <BarChart2 className="w-6 h-6 text-accent" />, text: 'Agent dashboards' },
  { icon: <MapPin className="w-6 h-6 text-accent" />, text: 'Geo-location & map view' },
  { icon: <Users className="w-6 h-6 text-accent" />, text: 'Booking & inquiry forms' },
];

const benefits = [
    { for: 'Agents', description: 'Manage your listings, track leads, and close deals faster with a comprehensive dashboard.' },
    { for: 'Buyers', description: 'Find your dream home with powerful search filters and detailed property information.' },
    { for: 'Renters', description: 'Discover available properties, schedule viewings, and apply online with ease.' },
]

const screenshots = [
  { src: 'https://placehold.co/1200x800', alt: 'Property listing page', dataHint: 'property listing' },
  { src: 'https://placehold.co/1200x800', alt: 'Agent dashboard', dataHint: 'dashboard analytics' },
  { src: 'https://placehold.co/1200x800', alt: 'Map view of properties', dataHint: 'city map' },
  { src: 'https://placehold.co/1200x800', alt: 'Booking form', dataHint: 'booking form' },
];

export default function RealEstateProductPage() {
  return (
    <>
      <section className="bg-secondary/50 py-20">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h1 className="font-headline text-4xl md:text-5xl font-bold text-primary">Smarter Property Management for Agents and Buyers</h1>
          <p className="mt-4 text-lg text-muted-foreground max-w-3xl mx-auto">
            NestEstate is a modern, intuitive platform designed to streamline real estate listing, management, and sales for agents, buyers, and renters.
          </p>
        </div>
      </section>

      <section className="py-16 md:py-24 bg-background">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center mb-12">
                <h2 className="font-headline text-3xl font-bold">Key Features</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
                {features.map((feature, index) => (
                    <Card key={index} className="border-0 shadow-lg">
                        <CardContent className="pt-6">
                            <div className="flex items-center gap-4">
                                {feature.icon}
                                <span className="font-semibold text-foreground">{feature.text}</span>
                            </div>
                        </CardContent>
                    </Card>
                ))}
            </div>
        </div>
      </section>

      <section className="py-16 md:py-24 bg-secondary/50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
           <PropertyFilter />
        </div>
      </section>

      <section className="py-16 md:py-24 bg-background">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
             <div className="text-center mb-12">
                <h2 className="font-headline text-3xl font-bold">Modern & Intuitive</h2>
                 <p className="mt-2 text-lg text-muted-foreground">Explore the clean interface of the NestEstate platform.</p>
            </div>
            <Carousel className="w-full" opts={{ loop: true }}>
                <CarouselContent>
                    {screenshots.map((img, index) => (
                    <CarouselItem key={index}>
                        <Card className="overflow-hidden">
                            <CardContent className="p-0">
                                <Image
                                    src={img.src}
                                    alt={img.alt}
                                    width={1200}
                                    height={800}
                                    className="w-full h-auto object-cover"
                                    data-ai-hint={img.dataHint}
                                />
                            </CardContent>
                        </Card>
                    </CarouselItem>
                    ))}
                </CarouselContent>
                <CarouselPrevious className="ml-16" />
                <CarouselNext className="mr-16" />
            </Carousel>
        </div>
      </section>

      <section className="py-16 md:py-24 bg-secondary/50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="font-headline text-3xl font-bold">Built for the Entire Market</h2>
            <p className="mt-2 text-lg text-muted-foreground">A toolkit that serves every stakeholder in the property journey.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {benefits.map((benefit) => (
              <Card key={benefit.for} className="text-center shadow-lg hover:shadow-xl transition-shadow bg-card">
                <CardHeader>
                  <CardTitle className="font-headline text-2xl flex items-center justify-center gap-2"><Users/> For {benefit.for}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-muted-foreground">{benefit.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-primary text-primary-foreground py-20">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="font-headline text-3xl md:text-4xl font-bold">Find or List Your Next Property with NestEstate</h2>
          <p className="text-lg opacity-80 mt-4 mb-8">
            Join the future of real estate. Try NestEstate today to experience a smarter way to manage properties.
          </p>
          <Button size="lg" asChild className="bg-accent text-accent-foreground hover:bg-accent/90">
            <Link href="/demo">Try NestEstate</Link>
          </Button>
        </div>
      </section>
    </>
  );
}
