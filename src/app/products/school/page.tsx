import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Check, Info, Library, DollarSign, Briefcase, Star, Users } from 'lucide-react';
import Link from 'next/link';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';


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

const pricingTiers = [
    {
        name: 'Basic Plan',
        price: '₦1,500,000',
        students: 'Up to 250 students',
        description: 'Ideal for small schools needing core management functionalities.',
        features: [
            'Core Modules Included',
            'Standard Technical Support',
        ],
        highlight: false,
    },
    {
        name: 'Standard Plan',
        price: '₦4,500,000',
        students: 'Up to 1,000 students',
        description: 'The most popular choice for medium-sized schools.',
        features: [
            'All Basic Plan Features',
            'Advanced Reporting & Analytics',
            'Dedicated Support',
            'Custom User Roles',
        ],
        highlight: true,
    },
    {
        name: 'Enterprise Plan',
        price: '₦6,500,000',
        students: '1,000+ students',
        description: 'A customizable solution for large, multi-campus institutions.',
        features: [
            'All Standard Plan Features',
            'Dedicated Account Manager',
            'Custom Integrations',
            'Priority Support',
        ],
        highlight: false,
    },
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

      <section id="features" className="py-16 md:py-24 bg-secondary/50">
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
      
      <section id="pricing" className="py-16 md:py-24 bg-background">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center mb-12">
                <h2 className="font-headline text-3xl md:text-4xl font-bold text-foreground">Pricing & Licensing</h2>
                <p className="text-lg text-muted-foreground mt-2 max-w-3xl mx-auto">
                    The NestEdge School Management Engine is available under a proprietary license. This means the software is owned by our company and a license is required for its use.
                </p>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
                {pricingTiers.map((tier) => (
                    <Card key={tier.name} className={`flex flex-col shadow-lg ${tier.highlight ? 'border-primary ring-2 ring-primary shadow-primary/20 -translate-y-4' : 'border-border'}`}>
                        {tier.highlight && (
                            <div className="bg-primary text-primary-foreground text-sm font-bold text-center py-1 rounded-t-lg">Most Popular</div>
                        )}
                        <CardHeader className="text-center">
                            <CardTitle className="font-headline text-2xl">{tier.name}</CardTitle>
                            <p className="text-muted-foreground">{tier.description}</p>
                        </CardHeader>
                        <CardContent className="flex flex-col flex-grow">
                            <div className="text-center my-4">
                               <p className="text-4xl font-bold">{tier.price}</p>
                               <p className="text-sm text-muted-foreground">One-time license fee</p>
                               <p className="font-semibold mt-1">{tier.students}</p>
                            </div>
                            <ul className="space-y-3 flex-grow">
                                {tier.features.map((feature) => (
                                    <li key={feature} className="flex items-start">
                                        <Check className="w-5 h-5 mr-2 text-green-500 mt-1 flex-shrink-0" />
                                        <span className="text-muted-foreground">{feature}</span>
                                    </li>
                                ))}
                            </ul>
                        </CardContent>
                        <div className="p-6 mt-4">
                            <Button className={`w-full ${tier.highlight ? 'bg-primary hover:bg-primary/90' : 'bg-accent text-accent-foreground hover:bg-accent/90'}`}>
                                Choose Plan
                            </Button>
                        </div>
                    </Card>
                ))}
            </div>

             <div className="mt-16 text-center">
                <Card className="inline-block p-6 shadow-lg bg-secondary/50">
                    <h3 className="font-headline text-xl font-bold">Termly Maintenance Fee</h3>
                    <p className="text-2xl font-bold text-primary mt-2">₦1,000 per student</p>
                    <p className="text-muted-foreground mt-1">This fee covers ongoing software updates, security enhancements, and continued support for each academic term.</p>
                </Card>
            </div>
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
