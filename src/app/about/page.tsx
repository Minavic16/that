import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import Image from 'next/image';

export default function AboutPage() {
  return (
    <>
      <section className="bg-primary text-primary-foreground py-20">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h1 className="font-headline text-4xl md:text-5xl font-bold">About NestEdge</h1>
          <p className="mt-4 text-lg text-primary-foreground/80 max-w-3xl mx-auto">
            Transforming essential systems through intelligent platforms.
          </p>
        </div>
      </section>

      <section className="py-16 md:py-24 bg-background">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-12 items-center">
            <div className="space-y-8">
              <Card className="border-0 shadow-lg">
                <CardHeader>
                  <CardTitle className="font-headline text-2xl">Our Mission</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-lg text-muted-foreground">
                    To build smart, scalable software solutions that simplify education and real estate systems for the modern world.
                  </p>
                </CardContent>
              </Card>
              <Card className="border-0 shadow-lg">
                <CardHeader>
                  <CardTitle className="font-headline text-2xl">Our Vision</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-lg text-muted-foreground">
                    To empower schools, agents, and communities through digital transformation.
                  </p>
                </CardContent>
              </Card>
            </div>
             <div className="relative h-96 w-full rounded-lg overflow-hidden shadow-2xl">
                <Image
                    src="https://placehold.co/600x400"
                    alt="Team working together"
                    layout="fill"
                    objectFit="cover"
                    data-ai-hint="team collaboration"
                />
            </div>
          </div>

          <div className="mt-24">
            <Card className="bg-card shadow-xl overflow-hidden">
                <div className="grid grid-cols-1 md:grid-cols-2">
                    <div className="p-8 md:p-12">
                        <h2 className="font-headline text-3xl font-bold text-foreground mb-4">Who We Are</h2>
                        <p className="text-muted-foreground mb-4">
                            NestEdge is a forward-thinking software company focused on transforming essential systems through intelligent platforms. From education to real estate, we create tools that make life simpler, more organized, and more connected.
                        </p>
                        <h3 className="font-headline text-2xl font-bold text-foreground mt-8 mb-4">Our Parent Company</h3>
                        <p className="text-muted-foreground">
                            NestEdge is a <strong>subsidiary of GMG</strong>, a trusted educational and innovation-focused organization. As part of the GMG ecosystem, NestEdge benefits from a strong foundation of excellence, community impact, and forward-looking leadership.
                        </p>
                    </div>
                     <div className="relative h-64 md:h-auto min-h-[300px]">
                        <Image
                            src="https://placehold.co/600x800"
                            alt="Modern office building"
                            layout="fill"
                            objectFit="cover"
                            data-ai-hint="modern architecture"
                        />
                    </div>
                </div>
            </Card>
          </div>
        </div>
      </section>
    </>
  );
}
