"use client";

import { useState, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Check, Users, ArrowRight, Bot, BarChart, ShieldCheck, MapPin } from 'lucide-react';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { PremiumAddOn } from '@/types';
import Link from 'next/link';

const baseTiers = [
    { name: 'Small Schools', students: '< 250', price: 1500000, features: ['Secure Authentication', 'Role-Specific Dashboards', 'Streamlined Management'] },
    { name: 'Medium Schools', students: '250–1,000', price: 4500000, features: ['All features from Small Schools'] },
    { name: 'Large Schools', students: '> 1,000', price: 6500000, features: ['All features from Medium Schools'] },
];

const premiumAddOns: PremiumAddOn[] = [
    { id: 'attendance', title: 'Smart Attendance Module', price: 300000, description: 'Automate attendance tracking.', highlight: 'Geo-tagging and QR codes' },
    { id: 'analytics', title: 'Advanced Reports & Analytics', price: 500000, description: 'Gain deeper strategic insights from your school\'s data.', highlight: 'Deeper strategic insights' },
    { id: 'ai-basic', title: 'AI Mode (Basic)', price: [300000, 750000], description: 'Provide instant support with an entry-level chatbot.', highlight: 'Entry-level chatbot for support' },
    { id: 'ai-premium', title: 'AI Mode (Premium)', price: 1500000, description: 'Leverage an advanced Gemini-powered assistant for complex tasks.', highlight: 'Advanced Gemini-powered assistant' },
];

export default function PricingCalculator() {
    const [studentCount, setStudentCount] = useState(100);
    const [staffCount, setStaffCount] = useState(10);
    const [selectedAddOns, setSelectedAddOns] = useState<Record<string, boolean>>({});

    const handleAddOnToggle = (id: string) => {
        setSelectedAddOns(prev => ({ ...prev, [id]: !prev[id] }));
    };

    const { basePrice, activeTier } = useMemo(() => {
        if (studentCount < 250) return { basePrice: 1500000, activeTier: 'Small Schools' };
        if (studentCount >= 250 && studentCount <= 1000) return { basePrice: 4500000, activeTier: 'Medium Schools' };
        return { basePrice: 6500000, activeTier: 'Large Schools' };
    }, [studentCount]);
    
    const addOnsTotal = useMemo(() => {
        return premiumAddOns.reduce((total, addOn) => {
            if (selectedAddOns[addOn.id]) {
                // For ranged price, we can't calculate it without more info, so we'll just ignore for now in total.
                // Or take an average, but it's better to prompt user to contact.
                if(Array.isArray(addOn.price)) return total;
                return total + addOn.price;
            }
            return total;
        }, 0);
    }, [selectedAddOns]);

    const termlyMaintenance = useMemo(() => {
        const studentFee = studentCount * 1000;
        const staffFee = staffCount * 2500;
        return studentFee + staffFee;
    }, [studentCount, staffCount]);
    
    const totalOneTimeCost = basePrice + addOnsTotal;

    const formatNaira = (amount: number) => `₦${amount.toLocaleString()}`;


    return (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
            {/* Left/Main column */}
            <div className="lg:col-span-2 space-y-8">
                 {/* Base Pricing */}
                <div>
                    <h3 className="font-headline text-2xl md:text-3xl font-bold mb-4 flex items-center gap-2"><Users /> Base Pricing (Annual)</h3>
                    <Card className="shadow-lg">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Tier</TableHead>
                                    <TableHead>School Size</TableHead>
                                    <TableHead>Key Features</TableHead>
                                    <TableHead className="text-right">License Fee</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {baseTiers.map(tier => (
                                    <TableRow key={tier.name} className={tier.name === activeTier ? 'bg-primary/10' : ''}>
                                        <TableCell className="font-semibold">{tier.name}</TableCell>
                                        <TableCell>{tier.students}</TableCell>
                                        <TableCell>{tier.features.join(', ')}</TableCell>
                                        <TableCell className="text-right font-bold">{formatNaira(tier.price)}</TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </Card>
                </div>

                {/* Premium Add-ons */}
                <div>
                    <h3 className="font-headline text-2xl md:text-3xl font-bold mb-4 flex items-center gap-2"><Star /> Premium Feature Add-ons (Annual)</h3>
                     <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {premiumAddOns.map(addOn => (
                            <Card key={addOn.id} className="shadow-lg flex flex-col">
                                <CardHeader>
                                    <CardTitle className="flex items-center justify-between">
                                        <span>{addOn.title}</span>
                                        <Switch
                                            checked={!!selectedAddOns[addOn.id]}
                                            onCheckedChange={() => handleAddOnToggle(addOn.id)}
                                            aria-label={`Toggle ${addOn.title}`}
                                        />
                                    </CardTitle>
                                </CardHeader>
                                <CardContent className="flex-grow">
                                    <p className="text-muted-foreground text-sm mb-2">{addOn.description}</p>
                                    <p className="font-semibold text-primary">
                                        {Array.isArray(addOn.price) ? `${formatNaira(addOn.price[0])} – ${formatNaira(addOn.price[1])}` : formatNaira(addOn.price)}
                                    </p>
                                    <p className="text-xs text-accent-foreground bg-accent/80 inline-block px-2 py-1 rounded-full mt-2">
                                        {addOn.highlight}
                                    </p>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                </div>

                {/* Termly Maintenance */}
                <div>
                     <h3 className="font-headline text-2xl md:text-3xl font-bold mb-4 flex items-center gap-2"><ShieldCheck /> Termly Maintenance Fee</h3>
                     <Card className="shadow-lg">
                        <CardContent className="pt-6">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-center">
                                <div>
                                    <p className="font-bold text-2xl text-primary">{formatNaira(1000)}</p>
                                    <p className="text-muted-foreground">per student, per term</p>
                                </div>
                                <div>
                                     <p className="font-bold text-2xl text-primary">{formatNaira(2500)}</p>
                                    <p className="text-muted-foreground">per staff, per term</p>
                                </div>
                            </div>
                            <p className="text-xs text-muted-foreground mt-4 text-center">
                                The per-staff fee is slightly higher due to increased system usage and access to advanced administrative features. This fee covers ongoing software updates, security enhancements, and dedicated support.
                            </p>
                        </CardContent>
                     </Card>
                </div>
            </div>

            {/* Right column - Calculator */}
            <div className="lg:col-span-1 sticky top-24">
                <Card className="shadow-2xl">
                    <CardHeader>
                        <CardTitle className="font-headline text-2xl text-center">Estimate Your Cost</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-6">
                         <div className="space-y-2">
                            <Label htmlFor="students">Number of Students</Label>
                            <Input id="students" type="number" value={studentCount} onChange={e => setStudentCount(Math.max(0, parseInt(e.target.value) || 0))} placeholder="e.g., 350" />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="staff">Number of Staff (Teachers & Admins)</Label>
                            <Input id="staff" type="number" value={staffCount} onChange={e => setStaffCount(Math.max(0, parseInt(e.target.value) || 0))} placeholder="e.g., 25" />
                        </div>
                        
                        <div className="border-t pt-4 space-y-4">
                            <h4 className="font-semibold text-center">Cost Summary</h4>
                            <div className="space-y-2">
                                <div className="flex justify-between">
                                    <span className="text-muted-foreground">One-time License Fee:</span>
                                    <span className="font-bold">{formatNaira(totalOneTimeCost)}</span>
                                </div>
                                <p className="text-xs text-muted-foreground pl-2">({activeTier}: {formatNaira(basePrice)} + Add-ons: {formatNaira(addOnsTotal)})</p>
                                
                                <div className="flex justify-between">
                                    <span className="text-muted-foreground">Estimated Termly Fee:</span>
                                    <span className="font-bold">{formatNaira(termlyMaintenance)}</span>
                                </div>
                            </div>

                            <div className="text-center bg-primary/10 p-4 rounded-lg">
                                <p className="text-sm text-primary font-semibold">Total Initial Cost (License + First Term)</p>
                                <p className="text-3xl font-bold text-primary">{formatNaira(totalOneTimeCost + termlyMaintenance)}</p>
                                <p className="text-xs text-muted-foreground">*Excludes AI Mode (Basic) if selected, as price varies. Contact us for a precise quote.</p>
                            </div>
                        </div>

                        <Button asChild size="lg" className="w-full bg-accent text-accent-foreground hover:bg-accent/90">
                            <Link href="/contact">Contact Us for a Quote <ArrowRight/></Link>
                        </Button>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
