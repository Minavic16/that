import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Check, Info, Library, DollarSign, Briefcase, Star, Users } from 'lucide-react';
import Link from 'next/link';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import PricingCalculator from '@/components/school/PricingCalculator';
import Image from 'next/image';
import { Carousel, CarouselContent, CarouselItem, CarouselNext, CarouselPrevious } from '@/components/ui/carousel';


const features = [
    {
        icon: <Info className="w-8 h-8 text-primary" />,
        title: "Student Information System",
        description: "A comprehensive module for managing student profiles, attendance, grades, and academic records seamlessly."
    },
    {
        icon: <Users className="w-8 h-8 text-primary" />,
        title: "Admission & Enrollment Management",
        description: "A powerful tool to handle the entire admission process, from application submission to final enrollment confirmation."
    },
    {
        icon: <DollarSign className="w-8 h-8 text-primary" />,
        title: "Finance & Fee Tracking",
        description: "An integrated system for managing tuition fees, processing payments, generating invoices, and creating financial reports."
    },
    {
        icon: <Briefcase className="w-8 h-8 text-primary" />,
        title: "Communication Hub",
        description: "A central feature that facilitates seamless communication between teachers, students, and parents through notifications, messaging, and announcements."
    },
    {
        icon: <Library className="w-8 h-8 text-primary" />,
        title: "Timetable & Scheduling",
        description: "An efficient module for creating and managing class schedules, teacher assignments, and important school events."
    },
];

const screenshots = [
  { src: 'https://firebasestudio.googleapis.com/v0/b/co-components-prod.appspot.com/o/images%2Fuser%2F1c37b848-a1c8-471a-942f-8796791f4b0f%2Fgenerated_1719597288673.png?alt=media&token=8e95793e-7a71-4603-9d95-8a2b53b84dd3', alt: 'School management dashboard', dataHint: 'dashboard analytics' },
  { src: 'https://placehold.co/1200x800', alt: 'Student profile page', dataHint: 'student profile' },
  { src: 'https://placehold.co/1200x800', alt: 'Finance tracking interface', dataHint: 'financial chart' },
];


export default function SchoolProductPage() {
  return (
    <>
      <section className="bg-primary text-primary-foreground py-20">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h1 className="font-headline text-4xl md:text-5xl font-bold">NestEdge School Management Engine</h1>
          <p className="mt-4 text-lg text-primary-foreground/80 max-w-3xl mx-auto">
            The all-in-one solution to streamline your school's success.
          </p>
        </div>
      </section>

      <section id="introduction" className="py-16 md:py-24 bg-background">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
            <Card className="shadow-lg border-0 p-8 md:p-12 bg-card">
                <CardHeader>
                    <CardTitle className="font-headline text-3xl text-center">Introduction</CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-lg text-muted-foreground text-center max-w-4xl mx-auto">
                        The NestEdge School Management Engine is a comprehensive, all-in-one solution designed to streamline administrative and academic tasks for educational institutions. With its user-friendly interface and scalable architecture, our platform improves efficiency, fosters communication, and empowers schools to focus on what matters most: education.
                    </p>
                </CardContent>
            </Card>
        </div>
      </section>
      
        <section className="py-16 md:py-24 bg-secondary/50">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
             <div className="text-center mb-12">
                <h2 className="font-headline text-3xl font-bold">A Glimpse Inside NestEdge</h2>
                 <p className="mt-2 text-lg text-muted-foreground">Explore the clean and powerful interface of our platform.</p>
            </div>
            <Carousel className="w-full" opts={{ loop: true }}>
                <CarouselContent>
                    {screenshots.map((img, index) => (
                    <CarouselItem key={index}>
                        <Card className="overflow-hidden shadow-xl">
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

      <section id="features" className="py-16 md:py-24 bg-background">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center mb-12">
                <h2 className="font-headline text-3xl md:text-4xl font-bold text-foreground">Key Features</h2>
                <p className="text-lg text-muted-foreground mt-2">The core functionalities of the application.</p>
            </div>
             <Accordion type="single" collapsible className="w-full space-y-4">
                {features.map((feature, index) => (
                   <AccordionItem key={index} value={`item-${index}`} className="bg-card border-0 rounded-lg shadow-md px-6">
                        <AccordionTrigger className="font-headline text-xl text-left hover:no-underline">
                             <div className="flex items-center gap-4">
                                {feature.icon}
                                <span>{feature.title}</span>
                            </div>
                        </AccordionTrigger>
                        <AccordionContent className="text-muted-foreground text-base pt-2">
                           {feature.description}
                        </AccordionContent>
                    </AccordionItem>
                ))}
            </Accordion>
        </div>
      </section>
      
      <section id="pricing" className="py-16 md:py-24 bg-secondary/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center mb-16">
                <h2 className="font-headline text-4xl md:text-5xl font-bold text-foreground">Transparent Pricing for Every School</h2>
                <p className="text-xl text-muted-foreground mt-4 max-w-3xl mx-auto">
                    Find the perfect plan for your institution. Our pricing is designed to be flexible and scalable.
                </p>
                 <p className="text-sm text-muted-foreground mt-2 max-w-3xl mx-auto">
                    The NestEdge School Management Engine is available under a proprietary license, requiring a one-time fee for lifetime ownership.
                </p>
            </div>

            <PricingCalculator />
            
        </div>
      </section>

      <section className="bg-primary text-primary-foreground py-20">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="font-headline text-3xl md:text-4xl font-bold">Ready to Transform Your School?</h2>
          <p className="text-lg opacity-80 mt-4 mb-8">
            Schedule a personalized demo or start a free trial to experience the power of NestEdge firsthand.
          </p>
          <Button size="lg" asChild className="bg-accent text-accent-foreground hover:bg-accent/90">
            <Link href="/demo">Request a Demo</Link>
          </Button>
        </div>
      </section>
    </>
  );
}
